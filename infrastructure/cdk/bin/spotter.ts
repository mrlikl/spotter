#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { SpotterStack } from "../lib/spotter-stack";

const app = new cdk.App();

new SpotterStack(app, "Spotter", {
  launchTemplateId: app.node.tryGetContext("launch-template-id"),
  clusterName: app.node.tryGetContext("cluster-name"),
  subnetIds: app.node.tryGetContext("subnet-ids"),
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: app.node.tryGetContext("region"),
  },
});