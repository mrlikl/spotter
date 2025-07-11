# Troubleshooting Guide

This document covers common issues you might encounter when deploying and using Spotter.

## Deployment Issues

### CDK Bootstrap Required

**Error:**

```
SSM parameter /cdk-bootstrap/hnb659fds/version not found. Has the environment been bootstrapped? Please run 'cdk bootstrap'
```

**Solution:**
CDK needs to be bootstrapped in your AWS account/region before first use:

```bash
cd infrastructure/cdk
npx cdk bootstrap
```

This creates the necessary S3 buckets, IAM roles, and other resources CDK needs for deployments.

## Lambda Function Issues

### EC2 Spot Service-Linked Role Permission Error

**Error:**

```json
{
  "statusCode": 500,
  "body": "{\"error\": \"An error occurred (AuthFailure.ServiceLinkedRoleCreationNotPermitted) when calling the RunInstances operation: The provided credentials do not have permission to create the service-linked role for EC2 Spot Instances.\"}"
}
```

**Root Cause:**
AWS requires a service-linked role for EC2 Spot instances, but your credentials don't have permission to create it automatically.

**Solution 1: Create Service-Linked Role Manually (Recommended)**

```bash
aws iam create-service-linked-role --aws-service-name spot.amazonaws.com
```

If the role already exists, you'll see a message indicating so - this is normal.

**Solution 2: Add IAM Permission**
If you have admin access, add this policy to your IAM user/role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iam:CreateServiceLinkedRole",
      "Resource": "arn:aws:iam::*:role/aws-service-role/spot.amazonaws.com/AWSServiceRoleForEC2Spot",
      "Condition": {
        "StringLike": {
          "iam:AWSServiceName": "spot.amazonaws.com"
        }
      }
    }
  ]
}
```

### InsufficientInstanceCapacity Errors

**Error in CloudWatch logs:**

```
InsufficientCapacity for m6g.large in us-west-2a, trying next instance
```

**Root Cause:**
AWS doesn't have enough capacity for the requested instance type in that availability zone.

**Solution:**
This is handled automatically by Spotter's fallback mechanism:

- InstanceRunner tries the next cheapest instance type
- If all instances in an AZ fail, check if other AZs have capacity
- Consider expanding your subnet configuration to more AZs

### No Instances Found in SSM

**Issue:**
Spotter Lambda runs but no instances are stored in SSM parameters.

**Debugging Steps:**

1. **Check Spotter Lambda logs:**

   ```bash
   aws logs tail /aws/lambda/Spotter --follow
   ```

2. **Verify minimum savings threshold:**
   The default is 80% savings. If spot prices aren't significantly cheaper than on-demand, no instances will be selected.

3. **Check instance filtering:**
   Spotter only considers:
   - ARM64 architecture
   - Current generation instances (c7g, c8g, m7g, m8g, r7g, r8g)
   - Non-burstable instances
   - Instances with < 110 pod capacity

## EKS Integration Issues

### Nodes Not Joining Cluster

**Issue:**
Instances launch successfully but don't appear in `kubectl get nodes`.

**Root Cause:**
The most common cause is that the node IAM role (`SpotterNodeRole`) is not authorized to join the EKS cluster.

**Solution 1: Add to EKS Access Entries (Recommended for EKS 1.23+)**

```bash
# Get the node role ARN
NODE_ROLE_ARN=$(aws iam get-role --role-name SpotterNodeRole --query 'Role.Arn' --output text)

# Add access entry for the node role
aws eks create-access-entry \
    --cluster-name YOUR_CLUSTER_NAME \
    --principal-arn $NODE_ROLE_ARN \
    --type EC2_LINUX
```

**Solution 2: Update aws-auth ConfigMap (For older EKS versions)**

```bash
# Edit the aws-auth configmap
kubectl edit configmap aws-auth -n kube-system
```

Add this section under `mapRoles`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: aws-auth
  namespace: kube-system
data:
  mapRoles: |
    - rolearn: arn:aws:iam::ACCOUNT_ID:role/SpotterNodeRole
      username: system:node:{{EC2PrivateDNSName}}
      groups:
        - system:bootstrappers
        - system:nodes
    # ... existing roles
```

Replace `ACCOUNT_ID` with your AWS account ID.

**Debugging Steps:**

1. **Check instance logs:**

   ```bash
   # SSH to instance or use Session Manager
   sudo journalctl -u kubelet -f
   ```

2. **Verify launch template configuration:**

   - Cluster name matches exactly
   - Security groups allow communication with EKS control plane
   - Subnets have route to internet (for pulling container images)

3. **Check EKS cluster endpoint access:**

   ```bash
   aws eks describe-cluster --name YOUR_CLUSTER_NAME --query 'cluster.endpoint'
   ```

4. **Verify node role permissions:**

   ```bash
   # Check if access entry exists
   aws eks list-access-entries --cluster-name YOUR_CLUSTER_NAME

   # Or check aws-auth configmap
   kubectl get configmap aws-auth -n kube-system -o yaml
   ```

**Common kubelet error messages:**

- `"Unauthorized"` - Node role not authorized to join cluster
- `"certificate verify failed"` - CA certificate mismatch
- `"connection refused"` - Security group or network connectivity issue

### Security Group Issues

**Issue:**
Nodes can't communicate with EKS control plane.

**Solution:**
Ensure the launch template uses the cluster security group:

- Check CloudFormation stack outputs for correct security group ID
- Verify security group allows HTTPS (443) traffic to EKS control plane

## Monitoring and Debugging

### Useful Commands

**Check SSM parameters:**

```bash
# List all Spotter parameters
aws ssm get-parameters-by-path --path "/spotter/spot" --recursive

# Check specific AZ
aws ssm get-parameter --name "/spotter/spot/us-west-2a"
```

**Monitor Lambda functions:**

```bash
# Tail logs in real-time
aws logs tail /aws/lambda/Spotter --follow
aws logs tail /aws/lambda/InstanceRunner --follow
```

**Check launched instances:**

```bash
# List Spotter-managed instances
aws ec2 describe-instances \
    --filters "Name=tag:ManagedBy,Values=Spotter" \
    --query 'Reservations[*].Instances[*].[InstanceId,InstanceType,State.Name,Placement.AvailabilityZone]' \
    --output table
```

**Verify EKS nodes:**

```bash
# Check Kubernetes nodes
kubectl get nodes -o wide

# Check node details
kubectl describe nodes
```

### Common Log Messages

**Normal Operations:**

- `"Filtered to X instance types"` - Spotter found eligible instances
- `"AZ us-west-2a: Found 6 top instances"` - Pricing analysis completed
- `"Launched m6g.large in us-west-2a: i-1234567890abcdef0"` - Instance launched successfully

**Warning Messages:**

- `"No instances found for AZ us-west-2a"` - No cost-effective instances in that AZ
- `"InsufficientCapacity for m6g.large"` - AWS capacity issue, trying fallback

**Error Messages:**

- `"Failed to launch any instance in us-west-2a"` - All instance types failed in that AZ
- `"No subnet found for AZ us-west-2a"` - Subnet configuration issue

## Getting Help

If you encounter issues not covered here:

1. **Check CloudWatch logs** for both Lambda functions
2. **Verify AWS permissions** for EC2, SSM, and IAM operations
3. **Ensure EKS cluster configuration** matches deployment parameters
4. **Test with smaller instance counts** first (e.g., `"instance_count": "1"`)

For additional support, check the project's GitHub issues or create a new issue with:

- Error messages from CloudWatch logs
- Your deployment configuration (cluster name, region, subnets)
- Output from the debugging commands above
