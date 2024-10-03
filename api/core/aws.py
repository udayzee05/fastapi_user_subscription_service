# app/aws_config.py

import boto3
import os
import logging
from botocore.exceptions import NoCredentialsError
from api.config import settings



class AWSConfig:
    def __init__(self):
        # Logger configuration for AWSConfig
        self.logger = logging.getLogger(__name__)
        self.session = boto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION
        )
        self.logger.info("AWS session initialized")

    def upload_to_s3(self, file_name, bucket_name, object_name=None):
        """
        Upload a file to an S3 bucket directly using session client.

        :param file_name: File to upload
        :param bucket_name: Bucket to upload to
        :param object_name: S3 object name. If not specified, file_name is used
        :return: URL of the uploaded file if successful, else None
        """
        if object_name is None:
            object_name = file_name

        self.logger.info(f"Uploading {file_name} to bucket {bucket_name}")
        s3_client = self.session.client('s3')
        try:
            s3_client.upload_file(file_name, bucket_name, object_name)
            location = s3_client.get_bucket_location(Bucket=bucket_name)['LocationConstraint']
            url = f"https://{bucket_name}.s3.{location}.amazonaws.com/{object_name}"
            self.logger.info(f"File uploaded successfully to {url}")
            return url
        except NoCredentialsError:
            self.logger.error("Credentials not available for AWS S3")
            return None
        except Exception as e:
            self.logger.error(f"Error uploading file to S3: {e}")
            return None
