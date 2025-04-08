import os
import boto3

def lambda_handler(event, context):
    sns_arn = os.environ.get("SNS_TOPIC_ARN")
    
    message = "TESTING: Lambda ran successfully!"
    
    sns = boto3.client("sns")
    sns.publish(
        TopicArn=sns_arn,
        Subject="Test: Lambda Alert",
        Message=message
    )
    
    return {
        "statusCode": 200,
        "body": "Notification sent."
    }
