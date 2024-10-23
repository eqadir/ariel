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
import { Observable, of, retry, switchMap, timer } from 'rxjs';
import { CONFIG } from '../../../../config';
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

  postToGcs(
    file: File,
    folder: string,
    filename: string,
    contentType?: string
  ): Observable<string[]> {
    // Determine the content type if not provided.
    if (!contentType) {
      if (file.type.startsWith('video/')) {
        contentType = file.type;
      } else if (file.type === 'application/json') {
        contentType = 'application/json';
      } else {
        throw new Error(
          `Unsupported file type: ${file.type}. Only video and JSON files are allowed.`
        );
      }
    }

    const fullName = encodeURIComponent(`${folder}/${filename}`);
    const url = `${CONFIG.cloudStorage.uploadEndpointBase}/b/${CONFIG.cloudStorage.bucket}/o?uploadType=media&name=${fullName}`;

    if (CONFIG.debug) {
      console.log(`Fullname: ${fullName}\nURL: ${url}`);
    }

    return this.getUserAuthToken().pipe(
      switchMap(userAuthToken =>
        this.httpClient
          .post(url, file, {
            headers: new HttpHeaders({
              'Authorization': `Bearer ${userAuthToken}`,
              'Content-Type': contentType,
            }),
          })
          .pipe(
            switchMap(response => {
              console.log('Upload complete!', response);
              const filePath = `${CONFIG.cloudStorage.authenticatedEndpointBase}/${CONFIG.cloudStorage.bucket}/${encodeURIComponent(folder)}/${filename}`;
              return of([folder, filePath]);
            })
          )
      )
    );
  }

  getFromGcs(url: string, retryDelay = 0, maxRetries = 0): Observable<string> {
    const gcsUrl = `${CONFIG.cloudStorage.endpointBase}/b/${CONFIG.cloudStorage.bucket}/o/${encodeURIComponent(url)}?alt=media`;

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

  downloadVideo(url: string, retryDelay = 0, maxRetries = 0): Observable<Blob> {
    const gcsUrl = `${CONFIG.cloudStorage.endpointBase}/b/${CONFIG.cloudStorage.bucket}/o/${encodeURIComponent(url)}?alt=media`;

    return this.getUserAuthToken().pipe(
      switchMap(userAuthToken =>
        this.httpClient.get(gcsUrl, {
          responseType: 'blob',
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

  // hello(): Observable<string> {
  //   return new Observable(subscriber => {
  //     // eslint-disable-next-line @typescript-eslint/ban-ts-comment
  //     // @ts-ignore
  //     google.script.run
  //       .withSuccessHandler((result: string) => {
  //         this.ngZone.run(() => {
  //           subscriber.next(result);
  //           subscriber.complete();
  //         });
  //       })
  //       .hello();
  //   });
  // }
}
