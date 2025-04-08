# AWS Underutilized Resource Detector

This project automatically detects underutilized AWS resources using a scheduled Lambda function, then sends alerts via SNS and tags those resources. It's built with **Python (Boto3)** for logic and **Terraform** for infrastructure provisioning.

## Features

- Detects **underutilized**:
  - EC2 instances (by CPU)
  - RDS databases (by CPU)
  - EBS volumes (by I/O activity)
  - ELBv2 Load Balancers (by request count)
- Tags underutilized EC2 & EBS volumes
- Sends daily email alerts using SNS
- Reports daily AWS cost via Cost Explorer
- Separates and reports **healthy (utilized)** resources for visibility

---

## Tech Stack

- **AWS Lambda (Python 3.11)**
- **CloudWatch Metrics**
- **Cost Explorer**
- **SNS**
- **Terraform** (infrastructure as code)

---

## How It Works

1. **CloudWatch Metrics** are used to check utilization:
   - CPU for EC2/RDS
   - VolumeReadOps & VolumeWriteOps for EBS
   - RequestCount for ELBv2

2. **Thresholds** (can be overridden via environment variables):
   ```
   EC2_CPU_THRESHOLD=10
   RDS_CPU_THRESHOLD=10
   EBS_IO_THRESHOLD=1
   ELB_REQUEST_THRESHOLD=1
   ```

3. **Underutilized resources**:
   - Are tagged with `Underutilized=True` and timestamp
   - Included in SNS alert

4. **Utilized (healthy)** resources:
   - Also listed in the email for transparency

---

## Alert Format

Example SNS email body:
```
UNDERUTILIZED AWS RESOURCES DETECTED
• EC2 Instance i-abc123: 4.5% avg CPU
• RDS Instance my-db: 8.9% avg CPU

Consider rightsizing or terminating these resources.

UTILIZED RESOURCES (HEALTHY)
• EBS Volume vol-xyz123: ReadOps: 250, WriteOps: 400 (OK)
• ELBv2 my-alb: 150 requests/hour (OK)

Estimated Daily AWS Cost: $0.32
```

---

![Screenshot 2025-04-08 at 2 59 13 PM](https://github.com/user-attachments/assets/61ef51fe-a77b-4514-a838-2cd297cd8291)


## Deployment (Terraform)

### Prerequisites:
- Terraform installed
- AWS CLI configured
- Your verified alert email

### Steps:

1. **Edit `terraform.tfvars`:**
   ```hcl
   alert_email = "you@example.com"
   ```

2. **Deploy:**
   ```bash
   terraform init
   terraform apply
   ```

3. **Confirm email subscription** from AWS SNS.

4. **Manually trigger the Lambda (optional):**
   ```bash
   aws lambda invoke --function-name underutilized-resource-checker output.txt
   ```

---

## Project Structure

```
.
├── main.py                  # Lambda function logic
├── lambda/                  # Zipped code directory
├── main.tf                  # All AWS infra (IAM, Lambda, SNS, etc.)
├── variables.tf             # Input variables (e.g., email)
├── terraform.tfvars         # Actual email value
```

---

## Notes

- The Lambda is scheduled to run **once daily**.
- You can reduce thresholds (e.g. `EC2_CPU_THRESHOLD=90`) to force alerts for testing.
- Costs shown are from **Cost Explorer** for the **previous day**.

---

## Author

Built by **Brennan Tong**

