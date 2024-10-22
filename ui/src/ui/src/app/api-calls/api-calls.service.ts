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
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, NgZone } from '@angular/core';
import { Observable, retry, switchMap, timer } from 'rxjs';
import { ApiCalls } from './api-calls.service.interface';

@Injectable({
  providedIn: 'root',
})
export class ApiCallsService implements ApiCalls {
  constructor(
    private ngZone: NgZone,
    private httpClient: HttpClient
  ) {}

  getUserAuthToken(): Observable<string> {
    return new Observable<string>(subscriber => {
      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-ignore
      google.script.run
        .withSuccessHandler((userAuthToken: string) => {
          this.ngZone.run(() => {
            subscriber.next(userAuthToken);
            subscriber.complete();
          });
        })
        .getUserAuthToken();
    });
  }
  getFromGcs(url: string, retryDelay = 0, maxRetries = 0): Observable<string> {
    // const gcsUrl = `${CONFIG.cloudStorage.endpointBase}/b/${CONFIG.cloudStorage.bucket}/o/${encodeURIComponent(url)}?alt=media`;
    const gcsUrl = '';

    return this.getUserAuthToken().pipe(
      switchMap(userAuthToken =>
        this.httpClient.get(gcsUrl, {
          responseType: 'text',
          headers: new HttpHeaders({
            Authorization: `Bearer ${userAuthToken}`,
          }),
        })
      ),
      retry({
        count: maxRetries,
        delay: (error, retryCount) => {
          if (
            (error.status && error.status !== 404) ||
            retryCount >= maxRetries
          ) {
            throw new Error(`Received an unexpected error: ${error}`);
          }
          return timer(retryDelay);
        },
      })
    );
  }

  generateUtterances(): Observable<string> {
    return new Observable(subscriber => {
      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-ignore
      google.script.run
        .withSuccessHandler((result: string) => {
          this.ngZone.run(() => {
            subscriber.next(result);
            subscriber.complete();
          });
        })
        .hello();
    });
  }

  hello(): Observable<string> {
    return new Observable(subscriber => {
      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-ignore
      google.script.run
        .withSuccessHandler((result: string) => {
          this.ngZone.run(() => {
            subscriber.next(result);
            subscriber.complete();
          });
        })
        .hello();
    });
  }
}
