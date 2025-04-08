import os
import boto3
from datetime import datetime, timedelta

# Configurable thresholds via environment variables
EC2_CPU_THRESHOLD = float(os.environ.get("EC2_CPU_THRESHOLD", 10))
RDS_CPU_THRESHOLD = float(os.environ.get("RDS_CPU_THRESHOLD", 10))
EBS_IO_THRESHOLD = float(os.environ.get("EBS_IO_THRESHOLD", 1))
ELB_REQUEST_THRESHOLD = float(os.environ.get("ELB_REQUEST_THRESHOLD", 1))

def get_avg_cpu_utilization(cloudwatch, namespace, metric_name, dimension_name, identifier):
    metrics = cloudwatch.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=[{"Name": dimension_name, "Value": identifier}], # Give stats for this specific instance ID
        StartTime=datetime.utcnow() - timedelta(hours=24), # StartTime/EndTime checks last 24 hours
        EndTime=datetime.utcnow(),
        Period=3600, # Every 1 hour
        Statistics=["Average"] # Get average CPU % in each period
    )
    
    datapoints = metrics["Datapoints"]
    if datapoints:
        avg_cpu = sum(dp["Average"] for dp in datapoints) / len(datapoints)
        return round(avg_cpu, 2)
    return None

def tag_resource(ec2_client, resource_id):
    tags = [
        {"Key": "Underutilized", "Value": "True"},
        {"Key": "FlaggedAt", "Value": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
    ]
    print("\nTagging resource as underutilized:")
    print(f"  - Resource ID: {resource_id}")
    print(f"  - Tags: {tags}\n")
    ec2_client.create_tags(Resources=[resource_id], Tags=tags)

def get_cost_estimate(ce_client):
    start = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
    end = datetime.utcnow().strftime('%Y-%m-%d')
    result = ce_client.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="DAILY",
        Metrics=["UnblendedCost"]
    )
    amount = result['ResultsByTime'][0]['Total']['UnblendedCost']['Amount']
    return round(float(amount), 2)

def lambda_handler(event, context):
    sns_arn = os.environ.get("SNS_TOPIC_ARN")
    cloudwatch = boto3.client("cloudwatch")
    ec2 = boto3.client("ec2")
    rds = boto3.client("rds")
    elbv2 = boto3.client("elbv2")
    sns = boto3.client("sns")
    ce = boto3.client("ce")  # Cost Explorer for future enhancements


    underutilized_resources = []

    # --- EC2 ---
    ec2_response = ec2.describe_instances(Filters=[
        {"Name": "instance-state-name", "Values": ["running"]}
    ])

    for reservation in ec2_response["Reservations"]:
        for instance in reservation["Instances"]:
            instance_id = instance["InstanceId"]
            avg_cpu = get_avg_cpu_utilization(cloudwatch, "AWS/EC2", "CPUUtilization", "InstanceId", instance_id)
            if avg_cpu is not None and avg_cpu < EC2_CPU_THRESHOLD:
                underutilized_resources.append(f"EC2 Instance {instance_id}: {avg_cpu}% avg CPU")
                tag_resource(ec2, instance_id)

    # --- RDS ---
    rds_response = rds.describe_db_instances()
    for db in rds_response["DBInstances"]:
        db_id = db["DBInstanceIdentifier"]
        avg_cpu = get_avg_cpu_utilization(cloudwatch, "AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", db_id)
        if avg_cpu is not None and avg_cpu < RDS_CPU_THRESHOLD:
            underutilized_resources.append(f"RDS Instance {db_id}: {avg_cpu}% avg CPU")

    # --- EBS ---
    volumes = ec2.describe_volumes(Filters=[
        {"Name": "status", "Values": ["in-use"]}
    ])["Volumes"]

    for vol in volumes:
        vol_id = vol["VolumeId"]
        read_ops = get_avg_cpu_utilization(cloudwatch, "AWS/EBS", "VolumeReadOps", "VolumeId", vol_id)
        write_ops = get_avg_cpu_utilization(cloudwatch, "AWS/EBS", "VolumeWriteOps", "VolumeId", vol_id)
        
        if (read_ops is not None and read_ops < EBS_IO_THRESHOLD) and (write_ops is not None and write_ops < EBS_IO_THRESHOLD):
            underutilized_resources.append(f"EBS Volume {vol_id}: Low I/O activity (ReadOps: {read_ops}, WriteOps: {write_ops})")
            tag_resource(ec2, vol_id)

    # --- ELBv2 (Application & Network Load Balancers) ---
    target_groups = elbv2.describe_target_groups()["TargetGroups"]

    for tg in target_groups:
        tg_name = tg["TargetGroupName"]
        lb_arn_suffix = tg["LoadBalancerArns"][0].split('/')[-1]  # For CloudWatch dimension

        # For ALB/NLB RequestCount
        requests = get_avg_cpu_utilization(
            cloudwatch,
            namespace="AWS/ApplicationELB",
            metric_name="RequestCount",
            dimension_name="LoadBalancer",
            identifier=lb_arn_suffix
        )

        if requests is not None and requests < ELB_REQUEST_THRESHOLD:
            underutilized_resources.append(f"ELBv2 {tg_name}: Low traffic ({requests} requests/hour)")

    # Cost Tracking
    estimated_cost = get_cost_estimate(ce)
    cost_summary = f"\nEstimated Daily AWS Cost: ${estimated_cost}"

    # --- Notify via SNS ---
    if underutilized_resources:
        header = "UNDERUTILIZED AWS RESOURCES DETECTED\n"
        body = "\n".join(f"• {r}" for r in underutilized_resources)
        cost_summary = f"\n\nEstimated Daily AWS Cost: ${estimated_cost}\n"
        footer = "\nConsider rightsizing or terminating these resources."

        message = header + body + cost_summary + footer

        print("Sending the following SNS alert:\n")
        print(message)
        sns.publish(
            TopicArn=sns_arn,
            Subject="AWS Underutilized Resource Alert",
            Message=message
        )

    return {
        "statusCode": 200,
        "body": "Utilization scan complete."
    }