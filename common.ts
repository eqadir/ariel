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

const fs = require("fs-extra");
const os = require("os");
const path = require("path");
const replace = require("replace");
const spawn = require("cross-spawn");

export const DEFAULT_GCP_REGION = "us-central1";
export const DEFAULT_GCS_LOCATION = "us";
export const DEFAULT_PUBSUB_TOPIC = "ariel-topic";
export const GCS_BUCKET_NAME_SUFFIX = "-ariel";
export const DEFAULT_CONFIGURE_APIS_AND_ROLES = true;
export const DEFAULT_USE_CLOUD_BUILD = true;

interface ConfigReplace {
  regex: string;
  replacement: string;
  paths: string[];
}

export interface PromptsResponse {
  gcpProjectId: string;
  gcpRegion?: string;
  gcsLocation?: string;
  pubsubTopic?: string;
  gcsBucket?: string;
  configureApisAndRoles?: boolean;
  useCloudBuild?: boolean;
  deployBackend?: boolean;
  deployUi?: boolean;
}

class ClaspManager {
  private static async isLoggedIn() {
    return await fs.exists(path.join(os.homedir(), ".clasprc.json"));
  }

  static async login() {
    const loggedIn = await this.isLoggedIn();

    if (!loggedIn) {
      console.log("Logging in via clasp...");
      spawn.sync("clasp", ["login"], { stdio: "inherit" });
    }
  }

  static async isConfigured(rootDir: string) {
    return (
      (await fs.exists(path.join(rootDir, ".clasp-dev.json"))) ||
      (await fs.exists(path.join(rootDir, "dist", ".clasp.json")))
    );
  }

  static extractSheetsLink(output: string) {
    const sheetsLink = output.match(/Google Sheet: ([^\n]*)/);

    return sheetsLink?.length ? sheetsLink[1] : "Not found";
  }

  static extractScriptLink(output: string) {
    const scriptLink = output.match(/Google Sheets Add-on script: ([^\n]*)/);

    return scriptLink?.length ? scriptLink[1] : "Not found";
  }

  static async create(
    title: string,
    scriptRootDir: string,
    filesRootDir: string
  ) {
    fs.ensureDirSync(path.join(filesRootDir, scriptRootDir));
    const res = spawn.sync(
      "clasp",
      [
        "create",
        "--type",
        "sheets",
        "--rootDir",
        scriptRootDir,
        "--title",
        title,
      ],
      { encoding: "utf-8" }
    );

    await fs.move(
      path.join(scriptRootDir, ".clasp.json"),
      path.join(filesRootDir, ".clasp-dev.json")
    );
    await fs.copyFile(
      path.join(filesRootDir, ".clasp-dev.json"),
      path.join(filesRootDir, ".clasp-prod.json")
    );
    await fs.remove(path.join(scriptRootDir, "appsscript.json"));
    const output = res.output.join();

    return {
      sheetLink: this.extractSheetsLink(output),
      scriptLink: this.extractScriptLink(output),
    };
  }
}

export class GcpDeploymentHandler {
  static async checkGcloudAuth() {
    const gcloudAuthExists = await fs.exists(
      path.join(os.homedir(), ".config", "gcloud", "credentials.db")
    );
    const gcloudAppDefaultCredsExists = await fs.exists(
      path.join(
        os.homedir(),
        ".config",
        "gcloud",
        "application_default_credentials.json"
      )
    );
    if (!gcloudAuthExists) {
      console.log("Logging in via gcloud...");
      spawn.sync("gcloud auth login", { stdio: "inherit", shell: true });
      console.log();
    }
    if (!gcloudAppDefaultCredsExists) {
      console.log(
        "Setting Application Default Credentials (ADC) via gcloud..."
      );
      spawn.sync("gcloud auth application-default login", {
        stdio: "inherit",
        shell: true,
      });
      console.log();
    }
  }

  static deployGcpComponents() {
    console.log(
      "Deploying Ariel Backend onto Google Cloud Platform..."
    );
    const res = spawn.sync("npm run deploy-backend", { stdio: "inherit", shell: true });
    if (res.status !== 0) {
      throw new Error("Failed to deploy GCP components.");
    }
  }
}

export class UiDeploymentHandler {
  static async createScriptProject() {
    console.log();
    await ClaspManager.login();

    const claspConfigExists = await ClaspManager.isConfigured("./ui");
    if (claspConfigExists) {
      return;
    }
    console.log();
    console.log("Creating Apps Script Project...");
    const res = await ClaspManager.create("Ariel", "./dist", "./ui");
    console.log();
    console.log("IMPORTANT -> Google Sheets Link:", res.sheetLink);
    console.log("IMPORTANT -> Apps Script Link:", res.scriptLink);
    console.log();
  }

  static deployUi() {
    console.log("Deploying the UI Web App...");
    spawn.sync("npm run deploy-ui", { stdio: "inherit", shell: true });
    const res = spawn.sync("cd ui && clasp undeploy -a && clasp deploy", {
      stdio: "pipe",
      shell: true,
      encoding: "utf8",
    });
    const lastNonEmptyLine = res.output[1]
      .split("\n")
      .findLast((line: string) => line.trim().length > 0);
    let webAppLink = lastNonEmptyLine.match(/- (.*) @.*/);
    webAppLink = webAppLink?.length
      ? `https://script.google.com/a/macros/google.com/s/${webAppLink[1]}/exec`
      : "Could not extract UI Web App link from npm output! Please check the output manually.";
    console.log();
    console.log(`IMPORTANT -> UI Web App Link: ${webAppLink}`);
  }
}

export class UserConfigManager {
  static alreadyCopiedFiles: string[] = [];

  static getCurrentConfig(){
    if(fs.existsSync(".config.json")){
      return JSON.parse(fs.readFileSync(".config.json"))
    } else {
      console.log("No config found, using default values");
      return {
        gcpRegion: DEFAULT_GCP_REGION,
        gcsLocation: DEFAULT_GCS_LOCATION,
        pubsubTopic: DEFAULT_PUBSUB_TOPIC,
        configureApisAndRoles: DEFAULT_CONFIGURE_APIS_AND_ROLES,
        useCloudBuild: DEFAULT_USE_CLOUD_BUILD,
      }
    }
  }

  static saveConfig(config: any){
    fs.writeFileSync(".config.json", JSON.stringify(config))
  }

  static setUserConfig(response: PromptsResponse) {
    const configReplace = (config: ConfigReplace) => {
      config.paths.forEach((path: string) => {
        if (!UserConfigManager.alreadyCopiedFiles.includes(path)) {
          console.log(`Copying the template: ${path}.TEMPLATE -> ${path}`);
          fs.copySync(`${path}.TEMPLATE`, path);
          UserConfigManager.alreadyCopiedFiles.push(path);
        }
      });

      replace({
        regex: config.regex,
        replacement: config.replacement,
        paths: config.paths,
        recursive: false,
        silent: true,
      });
    };

    console.log();
    console.log("Setting user configuration...");
    const gcpProjectId = response.gcpProjectId;
    const gcpRegion = response.gcpRegion || DEFAULT_GCP_REGION;
    const gcsLocation = response.gcsLocation || DEFAULT_GCS_LOCATION;
    const gcpProjectIdSanitized = `${gcpProjectId
      .replace("google.com:", "")
      .replace(".", "-")
      .replace(":", "-")}`;
    const gcsBucket = response.gcsBucket ||`${gcpProjectIdSanitized}${GCS_BUCKET_NAME_SUFFIX}`;
    const pubSubTopic = response.pubsubTopic || DEFAULT_PUBSUB_TOPIC;
    const configureApisAndRoles = response.configureApisAndRoles;
    const useCloudBuild = response.useCloudBuild;
    const deployUi = response.deployUi;
    const deployBackend = response.deployBackend;

    const config = {
      gcpProjectId: gcpProjectIdSanitized,
      gcpRegion: gcpRegion,
      gcsLocation: gcsLocation,
      pubsubTopic: pubSubTopic,
      gcsBucket: gcsBucket,
      configureApisAndRoles: configureApisAndRoles,
      useCloudBuild: useCloudBuild,
      deployUi: deployUi,
      deployBackend: deployBackend,
    }
    this.saveConfig(config)

    configReplace({
      regex: "<gcp-project-id>",
      replacement: gcpProjectId,
      paths: ["./backend/deploy-config.sh"],
    });

    configReplace({
      regex: "<gcp-region>",
      replacement: gcpRegion,
      paths: ["./backend/deploy-config.sh"],
    });

    configReplace({
      regex: "<gcs-location>",
      replacement: gcsLocation,
      paths: ["./backend/deploy-config.sh"],
    });

    configReplace({
      regex: "<gcs-bucket>",
      replacement: gcsBucket,
      paths: ["./backend/deploy-config.sh", "./ui/src/config.ts"],
    });

    configReplace({
      regex: "<pubsub-topic>",
      replacement: pubSubTopic,
      paths: ["./backend/deploy-config.sh"],
    });

    configReplace({
      regex: "<configure-apis-and-roles>",
      replacement: configureApisAndRoles ? "true" : "false",
      paths: ["./backend/deploy-config.sh"],
    });

    configReplace({
      regex: "<use-cloud-build>",
      replacement: useCloudBuild ? "true" : "false",
      paths: ["./backend/deploy-config.sh"],
    })

    console.log();
  }
}
