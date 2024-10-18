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

  generateUtterances(data: unknown): Observable<string> {
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
