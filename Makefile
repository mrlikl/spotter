# Colors
RED := \033[0;31m
GREEN := \033[0;32m
BLUE := \033[0;34m
YELLOW := \033[1;33m
CYAN := \033[0;36m
BOLD := \033[1m
NC := \033[0m

# Variables
STACK_NAME ?= SpotterNodeResources
CDK_STACK_NAME ?= Spotter
TEMPLATE_FILE ?= infrastructure/cfn/launch-template.yaml
CACHE_FILE := .spotter-cache

# Default target
.PHONY: all
all: deploy

# Interactive deployment with EKS cluster details and caching
.PHONY: deploy
deploy:
	@echo  "$(BOLD)$(BLUE)🚀 Spotter Deployment$(NC)"
	@echo  "$(CYAN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@if [ -f $(CACHE_FILE) ]; then \
		echo  "$(YELLOW)Found cached configuration:$(NC)"; \
		cached_cluster=$$(grep "CLUSTER_NAME=" $(CACHE_FILE) | cut -d'=' -f2); \
		cached_region=$$(grep "REGION=" $(CACHE_FILE) | cut -d'=' -f2); \
		cached_subnets=$$(grep "SUBNET_IDS=" $(CACHE_FILE) | cut -d'=' -f2 2>/dev/null || echo ""); \
		echo  "  Cluster: $(CYAN)$$cached_cluster$(NC)"; \
		echo  "  Region: $(CYAN)$$cached_region$(NC)"; \
		if [ -n "$$cached_subnets" ]; then \
			echo  "  Subnets: $(CYAN)$$cached_subnets$(NC)"; \
		fi; \
		echo ""; \
		printf "$(GREEN)EKS Cluster Name [$$cached_cluster]: $(NC)"; read cluster_name; \
		printf "$(GREEN)AWS Region [$$cached_region]: $(NC)"; read region; \
		if [ -z "$$cluster_name" ]; then cluster_name=$$cached_cluster; fi; \
		if [ -z "$$region" ]; then region=$$cached_region; fi; \
	else \
		printf "$(GREEN)EKS Cluster Name: $(NC)"; read cluster_name; \
		printf "$(GREEN)AWS Region: $(NC)"; read region; \
	fi; \
	echo "CLUSTER_NAME=$$cluster_name" > $(CACHE_FILE); \
	echo "REGION=$$region" >> $(CACHE_FILE); \
	echo  "$(BLUE)Using: Cluster=$(BOLD)$$cluster_name$(NC)$(BLUE), Region=$(BOLD)$$region$(NC)"; \
	echo  "$(BLUE)Getting cluster details...$(NC)"; \
	cluster_info=$$(aws eks describe-cluster --name $$cluster_name --region $$region --query '{endpoint:cluster.endpoint,caData:cluster.certificateAuthority.data,serviceCidr:cluster.kubernetesNetworkConfig.serviceIpv4Cidr,clusterSG:cluster.resourcesVpcConfig.clusterSecurityGroupId,vpc:cluster.resourcesVpcConfig.vpcId,version:cluster.version}' --output json); \
	endpoint=$$(echo $$cluster_info | jq -r '.endpoint'); \
	ca_data=$$(echo $$cluster_info | jq -r '.caData'); \
	service_cidr=$$(echo $$cluster_info | jq -r '.serviceCidr'); \
	cluster_sg=$$(echo $$cluster_info | jq -r '.clusterSG'); \
	vpcid=$$(echo $$cluster_info | jq -r '.vpc'); \
	version=$$(echo $$cluster_info | jq -r '.version'); \
	echo  "$(YELLOW)Cluster Details:$(NC)"; \
	echo "  Endpoint: $$endpoint"; \
	echo "  Region: $$region"; \
	echo "  K8s Version: $$version"; \
	echo "  CA Data: $$ca_data"; \
	echo "  Service CIDR: $$service_cidr"; \
	echo "  Cluster Security Group: $$cluster_sg"; \
	echo "  VPC Id: $$vpcid"; \
	echo "$(BLUE)Available subnets in VPC $$vpcid:$(NC)"; \
	aws ec2 describe-subnets \
		--filters "Name=vpc-id,Values=$$vpcid" "Name=state,Values=available" \
		--query 'Subnets[].{SubnetId:SubnetId,AZ:AvailabilityZone,CIDR:CidrBlock,Name:Tags[?Key==`Name`].Value|[0]}' \
		--output table --region $$region; \
	if [ -n "$$cached_subnets" ]; then \
		printf "$(GREEN)Subnet IDs (comma-separated) [$$cached_subnets]: $(NC)"; read subnet_ids; \
		if [ -z "$$subnet_ids" ]; then subnet_ids=$$cached_subnets; fi; \
	else \
		printf "$(GREEN)Subnet IDs (comma-separated): $(NC)"; read subnet_ids; \
	fi; \
	echo "SUBNET_IDS=$$subnet_ids" >> $(CACHE_FILE); \
	echo  "$(GREEN)Deploying CloudFormation launch template...$(NC)"; \
	aws cloudformation deploy \
		--template-file $(TEMPLATE_FILE) \
		--stack-name $(STACK_NAME) \
		--capabilities CAPABILITY_NAMED_IAM \
		--parameter-overrides ClusterSecurityGroup=$$cluster_sg VpcId=$$vpcid ClusterVersion=$$version ClusterCA=$$ca_data ClusterName=$$cluster_name ClusterEndpoint=$$endpoint ServiceCIDR=$$service_cidr \
		--tags spotter=owned \
		--region $$region; \
	echo  "$(GREEN)✅ CloudFormation deployed successfully$(NC)"; \
	echo  "$(CYAN)Getting launch template ID...$(NC)"; \
	LAUNCH_TEMPLATE_ID=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--region $$region \
		--query 'Stacks[0].Outputs[?OutputKey==`LaunchTemplateId`].OutputValue' \
		--output text); \
	echo  "$(YELLOW)Launch Template ID: $$LAUNCH_TEMPLATE_ID$(NC)"; \
	echo  "$(BLUE)Deploying CDK stack...$(NC)"; \
	cd infrastructure/cdk && \
	npm install && \
	npm run build && \
	cdk deploy $(CDK_STACK_NAME) \
		-c launch-template-id=$$LAUNCH_TEMPLATE_ID \
		-c cluster-name=$$cluster_name \
		-c region=$$region \
		-c subnet-ids="$$subnet_ids" \
		--require-approval never; \
	echo  "$(GREEN)🎉 Full deployment completed successfully!$(NC)"

# Deploy only CloudFormation (with caching)
.PHONY: deploy-cfn
deploy-cfn:
	@if [ -f $(CACHE_FILE) ]; then \
		cached_cluster=$$(grep "CLUSTER_NAME=" $(CACHE_FILE) | cut -d'=' -f2); \
		cached_region=$$(grep "REGION=" $(CACHE_FILE) | cut -d'=' -f2); \
		printf "$(GREEN)EKS Cluster Name [$$cached_cluster]: $(NC)"; read cluster_name; \
		printf "$(GREEN)AWS Region [$$cached_region]: $(NC)"; read region; \
		if [ -z "$$cluster_name" ]; then cluster_name=$$cached_cluster; fi; \
		if [ -z "$$region" ]; then region=$$cached_region; fi; \
	else \
		printf "$(GREEN)EKS Cluster Name: $(NC)"; read cluster_name; \
		printf "$(GREEN)AWS Region: $(NC)"; read region; \
	fi; \
	echo "CLUSTER_NAME=$$cluster_name" > $(CACHE_FILE); \
	echo "REGION=$$region" >> $(CACHE_FILE); \
	echo  "$(BLUE)Getting cluster details...$(NC)"; \
	cluster_info=$$(aws eks describe-cluster --name $$cluster_name --region $$region --query '{endpoint:cluster.endpoint,caData:cluster.certificateAuthority.data,serviceCidr:cluster.kubernetesNetworkConfig.serviceIpv4Cidr,clusterSG:cluster.resourcesVpcConfig.clusterSecurityGroupId,vpc:cluster.resourcesVpcConfig.vpcId,version:cluster.version}' --output json); \
	endpoint=$$(echo $$cluster_info | jq -r '.endpoint'); \
	ca_data=$$(echo $$cluster_info | jq -r '.caData'); \
	service_cidr=$$(echo $$cluster_info | jq -r '.serviceCidr'); \
	cluster_sg=$$(echo $$cluster_info | jq -r '.clusterSG'); \
	vpcid=$$(echo $$cluster_info | jq -r '.vpc'); \
	version=$$(echo $$cluster_info | jq -r '.version'); \
	aws cloudformation deploy \
		--template-file $(TEMPLATE_FILE) \
		--stack-name $(STACK_NAME) \
		--capabilities CAPABILITY_NAMED_IAM \
		--parameter-overrides ClusterSecurityGroup=$$cluster_sg VpcId=$$vpcid ClusterVersion=$$version ClusterCA=$$ca_data ClusterName=$$cluster_name ClusterEndpoint=$$endpoint ServiceCIDR=$$service_cidr \
		--tags spotter=owned \
		--region $$region

# Deploy only CDK (with caching)
.PHONY: deploy-cdk
deploy-cdk:
	@if [ -f $(CACHE_FILE) ]; then \
		cached_cluster=$$(grep "CLUSTER_NAME=" $(CACHE_FILE) | cut -d'=' -f2); \
		cached_region=$$(grep "REGION=" $(CACHE_FILE) | cut -d'=' -f2); \
		cached_subnets=$$(grep "SUBNET_IDS=" $(CACHE_FILE) | cut -d'=' -f2 2>/dev/null || echo ""); \
		printf "$(GREEN)EKS Cluster Name [$$cached_cluster]: $(NC)"; read cluster_name; \
		printf "$(GREEN)AWS Region [$$cached_region]: $(NC)"; read region; \
		if [ -n "$$cached_subnets" ]; then \
			printf "$(GREEN)Subnet IDs [$$cached_subnets]: $(NC)"; read subnet_ids; \
			if [ -z "$$subnet_ids" ]; then subnet_ids=$$cached_subnets; fi; \
		else \
			printf "$(GREEN)Subnet IDs (comma-separated): $(NC)"; read subnet_ids; \
		fi; \
		if [ -z "$$cluster_name" ]; then cluster_name=$$cached_cluster; fi; \
		if [ -z "$$region" ]; then region=$$cached_region; fi; \
	else \
		printf "$(GREEN)EKS Cluster Name: $(NC)"; read cluster_name; \
		printf "$(GREEN)AWS Region: $(NC)"; read region; \
		printf "$(GREEN)Subnet IDs (comma-separated): $(NC)"; read subnet_ids; \
	fi; \
	echo "CLUSTER_NAME=$$cluster_name" > $(CACHE_FILE); \
	echo "REGION=$$region" >> $(CACHE_FILE); \
	echo "SUBNET_IDS=$$subnet_ids" >> $(CACHE_FILE); \
	LAUNCH_TEMPLATE_ID=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--region $$region \
		--query 'Stacks[0].Outputs[?OutputKey==`LaunchTemplateId`].OutputValue' \
		--output text); \
	echo  "$(CYAN)Using Launch Template ID: $$LAUNCH_TEMPLATE_ID$(NC)"; \
	cd infrastructure/cdk && \
	npm install && \
	npm run build && \
	cdk deploy $(CDK_STACK_NAME) \
		-c launch-template-id=$$LAUNCH_TEMPLATE_ID \
		-c cluster-name=$$cluster_name \
		-c region=$$region \
		-c subnet-ids="$$subnet_ids" \
		--require-approval never

# Show cached values
.PHONY: show-cache
show-cache:
	@if [ -f $(CACHE_FILE) ]; then \
		echo  "$(BLUE)Cached configuration:$(NC)"; \
		cached_cluster=$$(grep "CLUSTER_NAME=" $(CACHE_FILE) | cut -d'=' -f2); \
		cached_region=$$(grep "REGION=" $(CACHE_FILE) | cut -d'=' -f2); \
		cached_subnets=$$(grep "SUBNET_IDS=" $(CACHE_FILE) | cut -d'=' -f2); \
		echo  "  Cluster: $(CYAN)$$cached_cluster$(NC)"; \
		echo  "  Region: $(CYAN)$$cached_region$(NC)"; \
		echo  "  Subnets: $(CYAN)$$cached_subnets$(NC)"; \
	else \
		echo  "$(YELLOW)No cache found$(NC)"; \
	fi

# Clear cache
.PHONY: clear-cache
clear-cache:
	@rm -f $(CACHE_FILE)
	@echo  "$(RED)Cache cleared$(NC)"

# Validate CloudFormation template
.PHONY: validate
validate:
	@echo  "$(BLUE)Validating CloudFormation template...$(NC)"
	aws cloudformation validate-template \
		--template-body file://$(TEMPLATE_FILE)
	@echo  "$(GREEN)✅ Template is valid$(NC)"

# Clean up all resources (with caching)
.PHONY: destroy
destroy:
	@if [ -f $(CACHE_FILE) ]; then \
		cached_region=$$(grep "REGION=" $(CACHE_FILE) | cut -d'=' -f2); \
		printf "$(GREEN)AWS Region [$$cached_region]: $(NC)"; read region; \
		if [ -z "$$region" ]; then region=$$cached_region; fi; \
	else \
		printf "$(GREEN)AWS Region: $(NC)"; read region; \
	fi; \
	echo  "$(RED)⚠️  This will destroy all Spotter resources!$(NC)"; \
	printf "$(RED)Are you sure? (y/N): $(NC)"; read confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		echo  "$(RED)Destroying CDK stack...$(NC)"; \
		cd infrastructure/cdk && cdk destroy $(CDK_STACK_NAME) --force; \
		echo  "$(RED)Destroying CloudFormation stack...$(NC)"; \
		aws cloudformation delete-stack --stack-name $(STACK_NAME) --region $$region; \
		echo  "$(YELLOW)Waiting for stack deletion...$(NC)"; \
		aws cloudformation wait stack-delete-complete --stack-name $(STACK_NAME) --region $$region; \
		echo  "$(GREEN)✅ All resources destroyed$(NC)"; \
	else \
		echo  "$(YELLOW)Destruction cancelled$(NC)"; \
	fi

# Help target
.PHONY: help
help:
	@echo  "$(BOLD)$(BLUE)Spotter Deployment Commands$(NC)"
	@echo  "$(CYAN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo  "  $(GREEN)deploy$(NC)           - Full deployment (CloudFormation + CDK)"
	@echo  "  $(GREEN)deploy-cfn$(NC)       - Deploy only CloudFormation launch template"
	@echo  "  $(GREEN)deploy-cdk$(NC)       - Deploy only CDK stack"
	@echo  "  $(GREEN)validate$(NC)         - Validate CloudFormation template"
	@echo  "  $(GREEN)show-cache$(NC)       - Show cached configuration"
	@echo  "  $(GREEN)clear-cache$(NC)      - Clear cached configuration"
	@echo  "  $(GREEN)destroy$(NC)          - Destroy all resources"
	@echo  "  $(GREEN)help$(NC)             - Show this help message"
	@echo  ""
	@echo  "$(BOLD)Variables:$(NC)"
	@echo  "  $(YELLOW)STACK_NAME$(NC)       - CloudFormation stack name (default: SpotterNodeResources)"
	@echo  "  $(YELLOW)CDK_STACK_NAME$(NC)   - CDK stack name (default: Spotter)"
	@echo  "  $(YELLOW)TEMPLATE_FILE$(NC)    - CloudFormation template path"
	@echo  ""
	@echo  "$(BOLD)Cache Usage:$(NC)"
	@echo  "  - Values are cached in $(YELLOW).spotter-cache$(NC)"
	@echo  "  - Press Enter to use cached values"
	@echo  "  - Enter new values to override cache"
