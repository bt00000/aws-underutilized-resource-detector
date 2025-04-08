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
    underutilized = []

    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instance_id = instance["InstanceId"]
            
            cpu = cloudwatch.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization"
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}], # Give stats for this specific instance ID
                StartTime=datetime.utcnow() - timedelta(hours=24), # StartTime/EndTime checks last 24 hours
                EndTime=datetime.utcnow(),
                Period = 3600, # Every 1 hour
                Statistics=["Average"] # Get average CPU % in each period
            )
