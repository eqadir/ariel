/**
 * Copyright 2024 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *       https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

const prompts = require("prompts");

import {
  AppsScriptDeploymentHandler,
  GcpDeploymentHandler,
  GCS_BUCKET_NAME_SUFFIX,
  UserConfigManager,
} from "./common.js";

(async () => {
  const config = UserConfigManager.getCurrentConfig()
  const response = await prompts([
    {
      type: "text",
      name: "gcpProjectId",
      message: `Enter your GCP Project ID [${config.gcpProjectId || "None"}]:`,
      initial: config.gcpProjectId || null,
      validate: (value: string) => (!value ? "Required" : true),
    },
    {
      type: "text",
      name: "gcsBucket",
      message: `Enter a GCS bucket name [${config.gcsBucket}]]:`,
      initial: (prev:string) => `${prev}${GCS_BUCKET_NAME_SUFFIX}`,
    },
    {
      type: "text",
      name: "gcpRegion",
      message: `Enter a GCP region for the Ariel to run in [${config.gcpRegion}]'):`,
      initial: config.gcpRegion,
    },
    {
      type: "text",
      name: "gcsLocation",
      message: `Enter a GCS location to store files in (can be multi-region like 'us' or 'eu' or single region like 'us-central1' or 'europe-west4') [${config.gcsLocation}]):`,
      initial: config.gcsLocation,
    },
    {
      type: "text",
      name: "pubsubTopic",
      message: `Enter a Pub/Sub Topic name [${config.pubsubTopic}]:`,
      initial: config.pubsubTopic,
    },
    {
      type: "toggle",
      name: "configureApisAndRoles",
      message: "Should APIs and Roles be configured? [Y/n]",
      initial: config.configureApisAndRoles,
      active: "yes",
      inactive: "no",
    },
    {
      type: "toggle",
      name: "useCloudBuild",
      message: "Should Ariel use Cloud Build? [Y/n]",
      initial: config.useCloudBuild,
      active: "yes",
      inactive: "no",
    }
  ]);
  UserConfigManager.setUserConfig(response);

  await GcpDeploymentHandler.checkGcloudAuth();
  GcpDeploymentHandler.deployGcpComponents();
  await AppsScriptDeploymentHandler.createScriptProject();
  AppsScriptDeploymentHandler.deployUi();
  // AppsScriptDeploymentHandler.printProjectLinks();
})();
