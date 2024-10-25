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
import { HttpClient } from '@angular/common/http';
import { Injectable, NgZone } from '@angular/core';
import { lastValueFrom, Observable, of } from 'rxjs';
import { ApiCalls } from './api-calls.service.interface';

@Injectable({
  providedIn: 'root',
})
export class ApiCallsService implements ApiCalls {
  constructor(
    private ngZone: NgZone,
    private httpClient: HttpClient
  ) {}

  getFromGcs(data: string, retryDelay = 0, maxRetries = 0): Observable<string> {
    return new Observable(subscriber => {
      console.log(
        `Generating utterances with the following config: ${data}, Retrydelay: ${retryDelay}, MaxRetries: ${maxRetries}`
      );
      setTimeout(() => {
        this.ngZone.run(async () => {
          subscriber.next(
            await this.loadLocalJsonFile('/assets/sample_utterances.json')
          );
          subscriber.complete();
        });
      }, 2000);
    });
  }

  downloadBlob(data: string, retryDelay = 0, maxRetries = 0): Observable<Blob> {
    return new Observable(subscriber => {
      console.log(
        `Fake downloading blob with the following settings: ${data}, Retrydelay: ${retryDelay}, MaxRetries: ${maxRetries}`
      );
      setTimeout(() => {
        this.ngZone.run(async () => {
          const localFile = data.endsWith('.mp4')
            ? '/assets/sample_video.mp4'
            : '/assets/sample_audio_chunk.mp3';

          subscriber.next(await this.loadLocalBlob(localFile));
          subscriber.complete();
        });
      }, 2000);
    });
  }

  postToGcs(
    file: File,
    folder: string,
    filename: string,
    contentType: string
  ): Observable<string[]> {
    console.log(
      `Running locally. Fake file uploaded: ${file.name}} with contentType ${contentType} `
    );
    return of([folder, filename]);
  }

  async loadLocalJsonFile(path: string) {
    const data = await lastValueFrom(
      this.httpClient.get(path, { responseType: 'text' })
    );
    return data;
  }

  async loadLocalBlob(path: string) {
    const data = await lastValueFrom(
      this.httpClient.get(path, { responseType: 'blob' })
    );
    return data;
  }

  hello(): Observable<string> {
    return new Observable(subscriber => {
      setTimeout(() => {
        this.ngZone.run(() => {
          subscriber.next('Hello Apps Script!');
          subscriber.complete();
        });
      }, 2000);
    });
  }
}
