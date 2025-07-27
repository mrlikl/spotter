# Spotter

**Production-grade spot instance scheduling for EKS worker nodes**

Spotter intelligently manages EC2 spot instances as EKS worker nodes, automatically finding the cheapest ARM64 instances across availability zones while handling interruptions gracefully. Achieves 70-80% cost savings over on-demand instances.

## Features

- **Real-time Pricing Analysis**: Continuous spot price monitoring with automatic instance selection
- **Multi-AZ Distribution**: Optimal instance placement across availability zones
- **Interruption Resilience**: Automatic replacement with fallback instance types
- **ARM64 Optimization**: Targets modern ARM64 families (c7g, c8g, m7g, m8g, r7g, r8g)
- **EKS Integration**: Native integration via CloudFormation launch templates

## Architecture

### Core Components

**Spotter Lambda**
- Analyzes spot pricing every 10 minutes
- Stores top 6 cheapest instances per AZ in SSM parameters
- Filters for ARM64, current-generation, non-burstable instances

**InstanceRunner Lambda**
- Launches instances based on pricing recommendations
- Handles spot interruption events with same-AZ replacement
- Implements intelligent fallback on Capacity issues

## Installation

### Prerequisites

- AWS CLI configured with appropriate permissions
- SAM CLI installed
- EKS cluster with kubectl access
- EC2 Spot service-linked role

```bash
pip install spotter-cli
```

### Quick Start


```bash
# Bootstrap Infrastructure
$ spotter bootstrap --region us-west-2

# Onboard EKS Cluster
$ spotter onboard my-cluster --region us-west-2

# Launch Instances
$ spotter scale my-cluster --count 3 --region us-west-2
```

### Scale to count

`--scale-to-count` will scale up or down to the `count` specified

```bash
$ spotter scale my-cluster --count 7 --scale-to-count --region us-west-2
```

### Commands
```bash
bootstrap        Deploy Spotter infrastructure
destroy          Destroy Spotter infrastructure
onboard          Onboard an EKS cluster to spotter
list-clusters    List onboarded clusters
offboard         Remove a cluster from Spotter
scale            Scale Spotter instances for a cluster
list-instances   Show current instance status for a cluster
rebalance        Rebalance instances across availability zones
refresh-prices   Refresh spot pricing data
pricing          View spot pricing data  
```

### Data Storage
Pricing data stored in SSM parameters:
- `/spotter/prices/{az}` - Top 6 instances per availability zone
- `/spotter/settings/{cluster}` - Cluster configuration


## Monitoring & Troubleshooting

### CloudWatch Logs
- `/aws/lambda/Spotter` - Pricing analysis logs
- `/aws/lambda/InstanceRunner` - Instance launch logs

### Troubleshooting
See [docs/troubleshooting.md](docs/troubleshooting.md) for comprehensive troubleshooting guidance.

## Cleanup

Remove all Spotter resources:
```bash
spotter destroy --region us-west-2
```

For cluster-specific cleanup:
```bash
spotter offboard my-cluster --region us-west-2
```

---

Vibe coded with [Amazon Q](https://github.com/aws/amazon-q-developer-cli)
