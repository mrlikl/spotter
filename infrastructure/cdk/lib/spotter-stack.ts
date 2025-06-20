import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as iam from "aws-cdk-lib/aws-iam";
import * as events from "aws-cdk-lib/aws-events";
import * as events_targets from "aws-cdk-lib/aws-events-targets";
import * as scheduler from "aws-cdk-lib/aws-scheduler";
import * as scheduler_targets from "aws-cdk-lib/aws-scheduler-targets";
import * as logs from "aws-cdk-lib/aws-logs"

export interface SpotterStackProps extends cdk.StackProps {
  /**
   * The minimum savings percentage to consider an instance
   * @default 80
   */
  readonly minSavingsPercent?: number;

  /**
   * The frequency to check spot prices in minutes
   * @default 10
   */
  readonly checkFrequencyMinutes?: number;

  /**
   * The Launch template to use for nodes
   */
  readonly launchTemplateId: string;

  /**
   * The Launch template to use for nodes
   */
  readonly clusterName: string;

  /**
   * Comma-separated Subnets Id's to launch nodes in
   */
  readonly subnetIds: string;
}

export class SpotterStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: SpotterStackProps) {
    super(scope, id, props);

    // Set default values
    const minSavingsPercent = props?.minSavingsPercent || 80;
    const checkFrequencyMinutes = props?.checkFrequencyMinutes || 10;

    const spotterLambdaFn = new lambda.Function(this, "SpotterLambda", {
      runtime: lambda.Runtime.PYTHON_3_13,
      code: lambda.Code.fromAsset("./lambda/spotter/"),
      functionName: 'Spotter',
      handler: "index.lambda_handler",
      timeout: cdk.Duration.seconds(90),
      logRetention: logs.RetentionDays.ONE_WEEK,
      environment: {
        MIN_SAVINGS_PERCENT: minSavingsPercent.toString(),
      },
    });

    spotterLambdaFn.addToRolePolicy(
      new cdk.aws_iam.PolicyStatement({
        actions: [
          "ec2:DescribeInstanceTypes",
          "ec2:DescribeSpotPriceHistory",
          "ssm:PutParameter",
          "pricing:GetProducts",
        ],
        resources: ["*"],
      })
    );

    const spotterTarget = new scheduler_targets.LambdaInvoke(spotterLambdaFn,{
      retryAttempts: 0,
    });

    new scheduler.Schedule(this, "SpotterSchedule", {
      schedule: scheduler.ScheduleExpression.rate(
        cdk.Duration.minutes(checkFrequencyMinutes)
      ),
      target: spotterTarget,
      description: `This is a schedule that invokes a lambda function every ${checkFrequencyMinutes} minutes.`,
    });

    const instanceRunnerFn = new lambda.Function(this, "InstanceRunner", {
      runtime: lambda.Runtime.PYTHON_3_13,
      handler: "index.lambda_handler",
      functionName: 'InstanceRunner',
      code: lambda.Code.fromAsset("./lambda/instancerunner/"),
      timeout: cdk.Duration.seconds(90),
      logRetention: logs.RetentionDays.ONE_WEEK,
      environment: {
        LAUNCH_TEMPLATE_ID: props.launchTemplateId,
        EKS_CLUSTER_NAME: props.clusterName,
        SUBNET_IDS: props.subnetIds,
        DESIRED_INSTANCE_COUNT: "1"
      },
    });

    instanceRunnerFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "ec2:RunInstances",
          "ec2:DescribeSubnets",
          "ec2:DescribeInstances",
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath",
          "ec2:CreateTags",
        ],
        resources: ["*"],
      })
    );
    instanceRunnerFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["iam:PassRole"],
        resources: ["*"],
        conditions: {
          StringEquals: {
            "iam:PassedToService": "ec2.amazonaws.com",
          },
        },
      })
    );

    const spotEventsRule = new events.Rule(this, "SpotEventsRule", {
      eventPattern: {
        source: ["aws.ec2"],
        detailType: ["EC2 Spot Instance Interruption Warning"],
      },
    });
    spotEventsRule.addTarget(
      new events_targets.LambdaFunction(instanceRunnerFn, {
        retryAttempts: 0,
      })
    );
  }
}
