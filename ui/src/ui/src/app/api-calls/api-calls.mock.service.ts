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
import { Observable, lastValueFrom } from 'rxjs';
import { ApiCalls } from './api-calls.service.interface';

@Injectable({
  providedIn: 'root',
})
export class ApiCallsService implements ApiCalls {
  constructor(
    private ngZone: NgZone,
    private httpClient: HttpClient
  ) {}

  generateUtterances(data: string): Observable<string> {
    return new Observable(subscriber => {
      console.log(`Generating utterances with the following config: ${data}`);
      setTimeout(() => {
        this.ngZone.run(async () => {
          subscriber.next(
            JSON.parse(
              await this.loadLocalFile('/assets/sample_utterances.json')
            )
          );
          subscriber.complete();
        });
      }, 2000);
    });
  }

  async loadLocalFile(path: string) {
    const data = await lastValueFrom(
      this.httpClient.get(path, { responseType: 'text' })
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
