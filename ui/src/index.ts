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

import { ScriptUtil } from './script-util';
/* eslint-disable @typescript-eslint/no-unused-vars */
function doGet() {
  return HtmlService.createTemplateFromFile('ui')
    .evaluate()
    .setTitle('Ariel - AI Video Ad Dubbing')
    .setFaviconUrl(
      'https://services.google.com/fh/files/misc/ariel_favicon.png'
    );
}
/* eslint-disable @typescript-eslint/no-unused-vars */
function include(filename: string) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function getUserAuthToken() {
  return ScriptUtil.getOAuthToken();
}
