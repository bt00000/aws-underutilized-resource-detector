import os
import boto3
from datetime import datetime, timedelta

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
    ec2_client.create_tags(Resources=[resource_id], Tags=tags)

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
            if avg_cpu is not None and avg_cpu < 10:
                underutilized_resources.append(f"EC2 Instance {instance_id}: {avg_cpu}% avg CPU")
                tag_resource(ec2, instance_id)

    # --- RDS ---
    rds_response = rds.describe_db_instances()
    for db in rds_response["DBInstances"]:
        db_id = db["DBInstanceIdentifier"]
        avg_cpu = get_avg_cpu_utilization(cloudwatch, "AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", db_id)
        if avg_cpu is not None and avg_cpu < 10:
            underutilized_resources.append(f"RDS Instance {db_id}: {avg_cpu}% avg CPU")

    # --- EBS ---
    volumes = ec2.describe_volumes(Filters=[
        {"Name": "status", "Values": ["in-use"]}
    ])["Volumes"]

    for vol in volumes:
        vol_id = vol["VolumeId"]
        read_ops = get_avg_cpu_utilization(cloudwatch, "AWS/EBS", "VolumeReadOps", "VolumeId", vol_id)
        write_ops = get_avg_cpu_utilization(cloudwatch, "AWS/EBS", "VolumeWriteOps", "VolumeId", vol_id)
        
        if (read_ops is not None and read_ops < 1) and (write_ops is not None and write_ops < 1):
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

        if requests is not None and requests < 1:
            underutilized_resources.append(f"ELBv2 {tg_name}: Low traffic ({requests} requests/hour)")

    # --- Notify via SNS ---
    if underutilized_resources:
        message = "Underutilized AWS Resources Detected:\n" + "\n".join(underutilized_resources)

        sns.publish(
            TopicArn=sns_arn,
            Subject="AWS Underutilized Resource Alert",
            Message=message
        )

    return {
        "statusCode": 200,
        "body": "Utilization scan complete."
    }