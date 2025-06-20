# Spotter

**Production-grade spot instance scheduling for EKS worker nodes**

Spotter is an intelligent, cost-optimized system for managing EC2 spot instances as EKS worker nodes. It automatically finds the cheapest ARM64 spot instances across availability zones, handles spot interruptions gracefully, and maintains cluster capacity with intelligent fallback mechanisms.

## 🚀 Features

- **Intelligent Pricing Analysis**: Real-time spot vs on-demand price comparison using AWS Pricing API
- **Multi-AZ Optimization**: Finds top 6 cheapest instances per availability zone
- **Smart Interruption Handling**: Automatically replaces interrupted instances with fallback options
- **ARM64 Focus**: Optimized for modern ARM64 instance families (c7g, c8g, m7g, m8g, r7g, r8g)
- **EKS Integration**: Seamless integration with existing EKS clusters via launch templates
- **Cost Savings**: Typically achieves 70-80% cost savings over on-demand instances

## 🏗️ Architecture

### Components

#### Spotter Lambda
- **Purpose**: Analyzes spot pricing and finds optimal instances
- **Frequency**: Runs every 10 minutes via EventBridge
- **Output**: Stores top 6 instances per AZ in SSM parameters (`/spotter/spot/{az}`)
- **Filters**: ARM64, current-generation, non-burstable instances

#### InstanceRunner Lambda
- **Purpose**: Launches spot instances based on Spotter recommendations
- **Triggers**: 
  - Manual with the payload `{ "instance_count": "6" }`
  - Spot interruption events (replaces in the same AZ)
- **Fallback**: Automatically tries next cheapest instance on InsufficientCapacity
- **Integration**: Uses CloudFormation launch templates for EKS node configuration

#### Pending Pod Controller (Kubernetes) (VIBE-CODING-IN-PROGRESS)
- **Purpose**: Monitors for pods stuck in FailedScheduling state
- **Action**: Sends notifications when additional nodes are needed

## 📁 Project Structure

```
spotter/
├── infrastructure/
│   ├── cfn/
│   │   └── launch-template.yaml      # EKS node launch template
│   ├── cdk/                          # CDK stack for Lambda functions
│   └── lambda/
│       ├── spotter/                  # Pricing analysis Lambda
│       └── instancerunner/           # Instance launching Lambda
├── k8s/                              # Kubernetes controller
├── deploy/                           # Deployment manifests
├── Makefile                          # Deployment automation
└── README.md
```

## ⚡️ Quick Start

### Prerequisites

- AWS CLI configured with appropriate permissions
- Node.js and npm installed
- CDK installed (`npm install -g aws-cdk`)
- kubectl configured for your EKS cluster
- jq installed for JSON processing

### Deployment

1. **Clone and setup**:
```bash
git clone https://github.com/mrlikl/spotter
cd spotter
```

2. **Deploy infrastructure**:
```bash
make deploy
```

This will:
- Prompt for EKS cluster name and region
- Fetch cluster details automatically
- Deploy CloudFormation launch template
- Prompts user for the Subnets to provision the nodes into
- Deploy CDK stack with Lambda functions
- Set up EventBridge rules for spot interruption handling

3. **Deploy Kubernetes controller** (work-in-progress):
```bash
kubectl apply -f deploy/kubernetes/
```

4. Run the lambda's initially 

Invoke Spotter 
```
aws lambda invoke --function-name Spotter response.json
```

Invoke Instance runner
```
aws lambda invoke \
    --function-name InstanceRunner \
    --payload '{ "instance_count": "6" }' \
    --cli-binary-format raw-in-base64-out \
    response.json
```
 
## 🔍 Instance Filtering

Spotter automatically filters instances based on:
- **Architecture**: ARM64 only
- **Families**: c7g, c8g, m7g, m8g, r7g, r8g
- **Generation**: Current generation only
- **Performance**: Non-burstable instances
- **EKS Compatibility**: Pod density < 110 pods per node

## 🔧 Troubleshooting

Instance data is stored in SSM for each AZ:
- `/spotter/spot/us-west-2a` - Top 3 instances for AZ A
- `/spotter/spot/us-west-2b` - Top 3 instances for AZ B
- `/spotter/spot/us-west-2c` - Top 3 instances for AZ C
- `/spotter/spot/us-west-2d` - Top 3 instances for AZ D

### Common Issues

1. **InsufficientCapacity errors**:
   - System automatically retries with next cheapest instance
   - Check CloudWatch logs for fallback attempts

2. **No instances found**:
   - Verify pricing API access and instance filtering criteria
   - Check minimum savings percentage threshold

### Debugging

```bash
# Check Lambda logs
aws logs tail /aws/lambda/Spotter --follow
aws logs tail /aws/lambda/InstanceRunner --follow

# Check SSM parameters
aws ssm get-parameter --name "/spotter/spot/us-west-2a"

# Verify launch template
aws ec2 describe-launch-templates --launch-template-ids lt-xxxxx
```

## 🧹 Cleanup

To remove all Spotter resources:

```bash
make destroy
```

This will:
- Destroy the CDK stack (Lambda functions, EventBridge rules)
- Delete the CloudFormation stack (launch template)
- Clean up all associated resources

---

Vibe coded with [Amazon Q](https://github.com/aws/amazon-q-developer-cli)