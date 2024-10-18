import { ApiCallsService } from '../app/api-calls/api-calls.service';

export const environment = {
  production: true,
  providers: [{ provide: ApiCallsService }],
};
