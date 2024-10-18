import { Observable } from 'rxjs';

export interface ApiCalls {
  hello(): Observable<string>;
}
