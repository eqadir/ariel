/**
 * Copyright 2024 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *       http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
import { HttpClientModule } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import {
  FormBuilder,
  FormsModule,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSliderModule } from '@angular/material/slider';
import { MatStepperModule } from '@angular/material/stepper';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { CONFIG } from '../../../config';
import { ApiCallsService } from './api-calls/api-calls.service';
import { Chip, InputChipsComponent } from './input-chips.component';

interface Dubbing {
  start: number;
  end: number;
  path: string;
  text: string;
  for_dubbing: boolean;
  speaker_id: string;
  ssml_gender: string;
  translated_text: string;
  assigned_voice: string;
  pitch: number;
  speed: number;
  volume_gain_db: number;
  adjust_speed: boolean;
  editing?: boolean;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    MatToolbarModule,
    MatIconModule,
    MatButtonModule,
    MatCardModule,
    MatInputModule,
    MatFormFieldModule,
    FormsModule,
    MatCheckboxModule,
    MatTooltipModule,
    MatSliderModule,
    InputChipsComponent,
    MatExpansionModule,
    HttpClientModule,
    MatStepperModule,
    ReactiveFormsModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css',
})
export class AppComponent {
  title = 'Ariel UI';
  preferredVoices: Chip[] = [
    { name: 'Journey' },
    { name: 'Studio' },
    { name: 'Wavenet' },
    { name: 'Polyglot' },
    { name: 'News' },
    { name: 'neural2' },
    { name: 'Standard' },
  ];
  loadingTranslations = false;
  loadingDubbedVideo = false;
  dubbingCompleted = false;
  selectedFile: File | null = null;

  readonly configPanelOpenState = signal(true);
  readonly videoSettingsPanelOpenState = signal(true);
  dubbedInstances!: Dubbing[];
  dubbedUrl: string = '';
  gcsFolder: string = '';

  constructor(
    // private http: HttpClient,
    private apiCalls: ApiCallsService
  ) {}

  onFileSelected(event: Event) {
    const inputElement = event.target as HTMLInputElement;
    if (inputElement && inputElement.files && inputElement.files.length > 0) {
      this.selectedFile = inputElement.files[0];
    } else {
      // Handle the case where the input element or files are null/undefined
      console.error('No file selected or target is not an input element.');
    }
  }

  // uploadVideo() {
  //   this.apiCalls
  //     .postToGcs(this.selectedFile!, this.gcsFolder, 'input.mp4')
  //     .subscribe(response => {
  //       console.log('Upload complete!', response);
  //     });
  // }

  toggleEdit(dubbing: Dubbing): void {
    dubbing.editing = !dubbing.editing;
  }

  private _formBuilder = inject(FormBuilder);

  configFormGroup = this._formBuilder.group({
    input_video: ['', Validators.required],
    advertiser_name: ['', Validators.required],
    original_language: ['de-DE', Validators.required],
    target_language: ['pl-PL', Validators.required],
    hugging_face_token: ['', Validators.required],
    number_of_speakers: [''],
    no_dubbing_phrases: [''],
    diarization_instructions: [''],
    translation_instructions: [''],
    merge_utterances: [''],
    minimum_merge_threshold: [''],
  });
  secondFormGroup = this._formBuilder.group({
    secondCtrl: ['', Validators.required],
  });

  dubVideo() {
    this.loadingDubbedVideo = true;
    this.dubbingCompleted = false;
    // Upload the (updated) utterances to gcs.
    this.apiCalls
      .postToGcs(
        this.jsonFile(
          JSON.stringify(this.dubbedInstances),
          'utterances_approved.json'
        ),
        this.gcsFolder,
        'utterances_approved.json'
      )
      .subscribe(response => {
        console.log('Approved utterances upload completed!', response);
        // Download final video.
        this.apiCalls
          .downloadVideo(`${this.gcsFolder}/dubbed_video.mp4`, 15000, 20)
          .subscribe(response => {
            console.log('Dubbed video generated!', response);
            this.loadingDubbedVideo = false;
            this.dubbingCompleted = true;
            this.dubbedUrl = URL.createObjectURL(response as unknown as Blob);
          });
      });
  }

  removeEmptyKeys(obj: object) {
    const result: { [key: string]: unknown } = {};
    for (const [key, value] of Object.entries(obj)) {
      if (key === 'input_video') {
        // Skip input_video as backend has own logic for it.
        continue;
      }
      if (value !== '') {
        result[key] = value;
      }
    }
    return result;
  }

  jsonFile(jsonString: string, filename: string): File {
    return new File([jsonString], filename, {
      type: 'application/json',
    });
  }

  generateUtterances() {
    if (this.selectedFile && this.configFormGroup.valid) {
      this.loadingTranslations = true;
      const configData = this.configFormGroup.value;
      const configDataJson = JSON.stringify(this.removeEmptyKeys(configData));
      const configDataFile = this.jsonFile(configDataJson, 'config.json');
      console.log(
        `Requested dubbing for video ${this.selectedFile.name} with the following config: ${configDataJson}`
      );
      // 1. Upload video to gcs.
      this.gcsFolder = `${this.selectedFile.name}${CONFIG.videoFolderNameSeparator}${Date.now()}`;
      this.apiCalls
        .postToGcs(this.selectedFile!, this.gcsFolder, 'input.mp4')
        .subscribe(response => {
          console.log('Video upload completed!', response);
          const folder = response[0];
          // 2. If video upload successfull, generate utterances.
          this.apiCalls
            .postToGcs(configDataFile, folder, 'config.json')
            .subscribe(data => {
              console.log('Configuration upload completed!', data);
              this.apiCalls
                .getFromGcs(`${this.gcsFolder}/utterances.json`, 15000, 20)
                .subscribe(response => {
                  console.log('Utterances generated!', response);
                  this.dubbedInstances = JSON.parse(
                    response
                  ) as unknown as Dubbing[];
                  this.loadingTranslations = false;
                });
            });
        });
    } else {
      // TODO(): Config form is invalid. Display error messages.
    }
  }
  isLinear = false;
}
