import os
import boto3
from datetime import datetime, timedelta

def lambda_handler(event, context):
    sns_arn = os.environ.get("SNS_TOPIC_ARN")
    cloudwatch = boto3.client("cloudwatch")
    ec2 = boto3.client("ec2")
    sns = boto3.client("sns")

    response = ec2.describe_instances(Filters=[
        {"Name": "instance-state-name", "Values": ["running"]}
    ])
    underutilized_instances = []

    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instance_id = instance["InstanceId"]
            
            cpu = cloudwatch.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}], # Give stats for this specific instance ID
                StartTime=datetime.utcnow() - timedelta(hours=24), # StartTime/EndTime checks last 24 hours
                EndTime=datetime.utcnow(),
                Period = 3600, # Every 1 hour
                Statistics=["Average"] # Get average CPU % in each period
            )

            datapoints = cpu["Datapoints"]
            if datapoints:
                avg_cpu = sum(dp["Average"] for dp in datapoints) / len(datapoints)
                if avg_cpu < 10: # If average CPU < 10%
                    underutilized_instances.append((instance_id, round(avg_cpu, 2))) # Mark it as underutilized and add to list
    
    if underutilized_instances:
        message = "The following EC2 instances are underutilized:\n"
        for instance_id, cpu in underutilized_instances:
            message += f"- {instance_id}: {cpu}% avg CPU\n"
        
        sns.publish(
            TopicArn=sns_arn,
            Subject="Underutilized EC2 Instance Detected",
            Message=message
        )

        return {
            "statusCode": 200,
            "body": "EC2 utilization check complete."
        }