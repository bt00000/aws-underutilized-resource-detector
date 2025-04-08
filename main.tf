provider "aws" {
  region = "us-east-1"
}

// IAM role that the Lambda function will assume
resource "aws_iam_role" "lambda_exec_role" {
  name = "my-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      },
      Action = "sts:AssumeRole"
    }]
  })
}

// IAM policy allowing Lambda to publish alerts to SNS
resource "aws_iam_policy" "sns_publish_policy" {
  name        = "sns-publish-policy"
  description = "Allows Lambda to publish to SNS"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = "sns:Publish",
        Resource = aws_sns_topic.alert_topic.arn
      }
    ]
  })
}

// Attach SNS policy to Lambda role
resource "aws_iam_role_policy_attachment" "attach_sns_publish_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.sns_publish_policy.arn
}

// Attach AWS-managed policy for basic Lambda logging
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

// Attach CloudWatch read-only access (for metrics)
resource "aws_iam_role_policy_attachment" "lambda_ec2_cloudwatch" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchReadOnlyAccess"
}

// Custom policy for EC2 info access (used in EC2 + EBS analysis)
resource "aws_iam_policy" "ec2_read_policy" {
  name        = "ec2-read-policy"
  description = "Allows Lambda to read EC2 instance info"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeRegions",
          "ec2:DescribeTags",
          "ec2:DescribeVolumes",
          "ec2:DescribeVolumeStatus"
        ],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_ec2_read_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.ec2_read_policy.arn
}

// Custom policy for allowing tagging EC2 & EBS resources
resource "aws_iam_policy" "ec2_tag_policy" {
  name        = "ec2-tag-policy"
  description = "Allows Lambda to tag EC2 instances and volumes"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "ec2:CreateTags"
        ],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_ec2_tag_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.ec2_tag_policy.arn
}

// Allow Lambda to describe RDS instances
resource "aws_iam_policy" "rds_read_policy" {
  name        = "rds-read-policy"
  description = "Allows Lambda to read RDS instance info"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "rds:DescribeDBInstances"
        ],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_rds_read_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.rds_read_policy.arn
}

// Allow Lambda to access ELBv2 metrics for utilization
resource "aws_iam_policy" "elbv2_read_policy" {
  name        = "elbv2-read-policy"
  description = "Allows Lambda to read ELBv2 info"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "elasticloadbalancing:DescribeLoadBalancers",
          "elasticloadbalancing:DescribeTargetGroups",
          "elasticloadbalancing:DescribeTargetHealth"
        ],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_elbv2_read_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.elbv2_read_policy.arn
}

// Allow Lambda to query AWS Cost Explorer
resource "aws_iam_policy" "cost_explorer_policy" {
  name        = "cost-explorer-policy"
  description = "Allows Lambda to fetch AWS cost data"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "ce:GetCostAndUsage"
        ],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_cost_explorer_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.cost_explorer_policy.arn
}

// SNS topic to receive underutilized resource alerts
resource "aws_sns_topic" "alert_topic" {
  name = "underutilized-resource-alerts"
}

// Subscribe your email to the SNS topic
resource "aws_sns_topic_subscription" "email_alert" {
  topic_arn = aws_sns_topic.alert_topic.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

// Deploy the Python Lambda that checks for underutilized resources
resource "aws_lambda_function" "resource_checker" {
  function_name = "underutilized-resource-checker"
  handler       = "main.lambda_handler"
  runtime       = "python3.11"
  role          = aws_iam_role.lambda_exec_role.arn
  filename      = "${path.module}/lambda/lambda.zip"

  source_code_hash = filebase64sha256("${path.module}/lambda/lambda.zip")

  timeout = 60

  environment {
    variables = {
      SNS_TOPIC_ARN = aws_sns_topic.alert_topic.arn
    }
  }
}

// CloudWatch rule to trigger Lambda once per day
resource "aws_cloudwatch_event_rule" "daily_trigger" {
  name                = "daily-resource-check"
  schedule_expression = "rate(1 day)"
}

// Target Lambda for the CloudWatch trigger
resource "aws_cloudwatch_event_target" "lambda_trigger" {
  rule      = aws_cloudwatch_event_rule.daily_trigger.name
  target_id = "check-underutilized"
  arn       = aws_lambda_function.resource_checker.arn
}

// Allow CloudWatch Events to invoke Lambda
resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.resource_checker.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trigger.arn
}

// Test instances
resource "aws_instance" "test_instance" {
  ami           = "ami-0c02fb55956c7d316" # Amazon Linux 2
  instance_type = "t2.micro"

  tags = {
    Name = "TestInstance"
  }
}

// RDS test instance
resource "aws_db_instance" "test_rds" {
  allocated_storage   = 20
  engine              = "mysql"
  engine_version      = "8.0"
  instance_class      = "db.t3.micro"
  db_name             = "testdb"
  username            = "admin"
  password            = "password123"
  skip_final_snapshot = true
  publicly_accessible = true

  tags = {
    Name = "TestRDS"
  }
}

// EBS volume + attachment to EC2
resource "aws_ebs_volume" "test_volume" {
  availability_zone = aws_instance.test_instance.availability_zone
  size              = 1

  tags = {
    Name = "TestVolume"
  }
}

resource "aws_volume_attachment" "test_attachment" {
  device_name = "/dev/sdh"
  volume_id   = aws_ebs_volume.test_volume.id
  instance_id = aws_instance.test_instance.id
}

// Networking setup for ALB (uses default VPC)
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

// Security group to allow HTTP for ALB + EC2
resource "aws_security_group" "alb_sg" {
  name        = "alb-sg"
  description = "Allow HTTP"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

// ELBv2 Application Load Balancer
resource "aws_lb" "test_alb" {
  name               = "test-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = data.aws_subnets.default.ids
}

// Target Group for ALB
resource "aws_lb_target_group" "test_tg" {
  name     = "test-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = data.aws_vpc.default.id
}

// Listener
resource "aws_lb_listener" "test_listener" {
  load_balancer_arn = aws_lb.test_alb.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.test_tg.arn
  }
}

// Register EC2 instance to target group
resource "aws_lb_target_group_attachment" "test_tg_attachment" {
  target_group_arn = aws_lb_target_group.test_tg.arn
  target_id        = aws_instance.test_instance.id
  port             = 80
}

