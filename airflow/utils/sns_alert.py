"""
AWS SNS Notification Helper
"""

import os
import boto3
from dotenv import load_dotenv

load_dotenv()


class SNSAlert:

    def __init__(self):

        self.client = boto3.client(

            "sns",

            region_name=os.getenv("AWS_REGION"),

            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),

            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),

        )

        self.topic = os.getenv("SNS_TOPIC_ARN")


    def send(self, subject, message):

        if not self.topic:

            print("SNS_TOPIC_ARN not configured.")

            return

        self.client.publish(

            TopicArn=self.topic,

            Subject=subject,

            Message=message

        )