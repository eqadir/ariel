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
