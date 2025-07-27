# Troubleshooting Guide

This document covers common issues when deploying and operating Spotter in production environments.

## Bootstrap Issues

### SAM CLI Not Found

**Error:**
```
❌ SAM CLI not found
```

**Solution:**
Install SAM CLI following AWS documentation:
```bash
# macOS
brew install aws-sam-cli

# Linux/Windows
# Follow: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html
```

### CloudFormation Deployment Failures

**Error:**
```
CloudFormation deployment failed
```

**Debugging:**
1. Check CloudFormation console for detailed error messages
2. Verify IAM permissions for CloudFormation operations
3. Ensure unique stack names across regions

**Common causes:**
- Insufficient IAM permissions
- Resource limits exceeded
- Invalid parameter values

## Lambda Function Issues

### EC2 Spot Service-Linked Role Missing

**Error:**
```json
{
  "error": "AuthFailure.ServiceLinkedRoleCreationNotPermitted when calling the RunInstances operation"
}
```

**Solution:**
Create the service-linked role manually:
```bash
aws iam create-service-linked-role --aws-service-name spot.amazonaws.com
```

### InsufficientInstanceCapacity

**Error in logs:**
```
InsufficientCapacity for m6g.large in us-west-2a, trying next instance
```

**Behavior:**
- Spotter automatically tries the next cheapest instance type
- If all instances in an AZ fail, operation continues with other AZs
- This is normal AWS behavior during high demand periods

**Mitigation:**
- Use multiple availability zones
- Consider expanding instance type selection criteria
- Monitor capacity trends in CloudWatch

### No Instances Found in SSM

**Issue:**
Spotter Lambda runs but no pricing data appears in SSM parameters.

**Debugging:**
```bash
# Refresh prices 
$ spotter refresh-prices --region us-west-2

# Check Spotter Lambda logs
aws logs tail /aws/lambda/Spotter --follow

# Verify SSM parameters
aws ssm get-parameters-by-path --path "/spotter/prices" --recursive
```

**Common causes:**
- Minimum savings threshold not met (default: 80%)
- No ARM64 instances available in region
- Spot prices higher than on-demand

## EKS Integration Issues

Refer to https://repost.aws/knowledge-center/eks-worker-nodes-cluster 
## Cluster Operations Issues

### Cluster Not Onboarded

**Error:**
```
Cluster CLUSTER not onboarded
```

**Solution:**
Onboard the cluster first:
```bash
spotter onboard CLUSTER_NAME --region REGION
```

**Verification:**
```bash
# Check cluster settings in SSM
aws ssm get-parameter --name "/spotter/settings/CLUSTER_NAME"

# List onboarded clusters
spotter list-clusters --region REGION
```

### Subnet Configuration Issues

**Error:**
```
No subnet found for AZ us-west-2a
```

**Debugging:**
```bash
# Check cluster settings
aws ssm get-parameter --name "/spotter/settings/CLUSTER_NAME" \
  --query 'Parameter.Value' --output text | jq '.subnet_map'

# Verify subnets exist
aws ec2 describe-subnets --subnet-ids subnet-12345
```

**Solution:**
Re-onboard cluster with correct subnet configuration:
```bash
spotter offboard CLUSTER_NAME --region REGION
spotter onboard CLUSTER_NAME --region REGION --subnets subnet-1,subnet-2,subnet-3
```

## Monitoring and Debugging

### CloudWatch Logs

**Spotter Lambda logs:**
```bash
aws logs tail /aws/lambda/Spotter --follow
```

**InstanceRunner Lambda logs:**
```bash
aws logs tail /aws/lambda/InstanceRunner --follow
```

### Instance Verification

**Check Spotter-managed instances:**
```bash
aws ec2 describe-instances \
  --filters "Name=tag:managedby,Values=spotter" \
  --query 'Reservations[*].Instances[*].[InstanceId,InstanceType,State.Name,Placement.AvailabilityZone]' \
  --output table
```

**Verify EKS nodes:**
```bash
kubectl get nodes -o wide
kubectl describe nodes
```

### SSM Parameter Verification

**Check pricing data:**
```bash
# List all pricing parameters
aws ssm get-parameters-by-path --path "/spotter/prices" --recursive

# Check specific AZ
aws ssm get-parameter --name "/spotter/prices/us-west-2a" \
  --query 'Parameter.Value' --output text | jq '.'
```

**Check cluster settings:**
```bash
aws ssm get-parameter --name "/spotter/settings/CLUSTER_NAME" \
  --query 'Parameter.Value' --output text | jq '.'
```

## Common Log Messages

### Normal Operations
- `"Filtered to X instance types"` - Instance filtering completed
- `"AZ us-west-2a: Found 6 top instances"` - Pricing analysis successful
- `"Launched m6g.large in us-west-2a: i-1234567890abcdef0"` - Instance launched

### Warning Messages
- `"No instances found for AZ us-west-2a"` - No cost-effective instances available
- `"InsufficientCapacity for m6g.large"` - AWS capacity constraint, trying fallback
- `"Warning: Only found X instances in AZ"` - Fewer instances available than requested

### Error Messages
- `"Failed to launch any instance in us-west-2a"` - All instance types failed
- `"Cluster CLUSTER not onboarded"` - Missing cluster configuration
- `"Lambda invocation failed"` - InstanceRunner execution error

## Performance Optimization

### Pricing Analysis Frequency

Default: 10 minutes. Adjust during bootstrap:
```bash
spotter bootstrap --region REGION --check-frequency 5
```

### Instance Selection Tuning

Adjust minimum savings threshold:
```bash
spotter bootstrap --region REGION --min-savings 70
```

### Multi-AZ Distribution

Ensure balanced distribution:
```bash
spotter rebalance CLUSTER_NAME --region REGION
```

## Production Considerations

### Monitoring Setup
- Set up CloudWatch alarms for Lambda function errors
- Monitor spot interruption rates via CloudWatch metrics
- Track cost savings with AWS Cost Explorer

### Capacity Planning
- Monitor `InsufficientCapacity` errors in logs
- Consider multiple instance families for better availability
- Use multiple availability zones for resilience

### Security
- Regularly review IAM permissions
- Monitor CloudTrail for Spotter-related API calls
- Ensure launch templates use latest EKS-optimized AMIs

## Getting Support

For issues not covered in this guide:

1. **Check CloudWatch logs** for both Lambda functions
2. **Verify AWS service quotas** for EC2 and EKS
3. **Test with minimal configuration** first

Include the following information when reporting issues:
- Error messages from CloudWatch logs
- Cluster configuration (region, subnets, instance types)
- Output from debugging commands above
