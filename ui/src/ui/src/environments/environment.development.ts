import { ApiCallsService as MockApiCallsService } from '../app/api-calls/api-calls.mock.service';
import { ApiCallsService } from '../app/api-calls/api-calls.service';

export const environment = {
  production: false,
  providers: [{ provide: ApiCallsService, useExisting: MockApiCallsService }],
};
