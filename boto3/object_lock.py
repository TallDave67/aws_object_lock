import boto3
import os
import sys
import json
import uuid

def generate_bucket_unique_name(bucket_base_name, tag):
    # Generate a GUID
    guid = str(uuid.uuid4())

    # Append the GUID to the base name
    unique_name = f"{bucket_base_name}-{tag}-{guid}"

    # AWS S3 bucket names must be between 3 and 63 characters long
    # and can contain only lowercase letters, numbers, hyphens, and periods
    # Ensure the name length is within limits and replace any invalid characters
    unique_name = unique_name[:63].lower().replace('_', '-').replace('.', '-')

    return unique_name

def enable_versioning(s3, bucket_name):
    """
    Enable versioning on the specified S3 bucket.
    
    Args:
    - s3 (object): instance of connection to AWS S3 service
    - bucket_name (str): The name of the S3 bucket for which to enable versioning.
    """
    result=True
    try:
        s3.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={
                'MFADelete': 'Disabled',
                'Status': 'Enabled',
            }
        )
        print(f"Versioning enabled for bucket '{bucket_name}'.")
    except Exception as e:
        print(f"Error enabling versioning for bucket '{bucket_name}': {e}")
        result=False
    return result

def create_object_lock_configuration(lock_mode, retention_units, retention_length):
    object_lock_configuration = {
        "ObjectLockEnabled": "Enabled",
        "Rule": {
            "DefaultRetention": {
                "Mode": lock_mode,
                retention_units: retention_length
            }
        }
    }
    print("object_lock_configuration", object_lock_configuration)
    return object_lock_configuration

def apply_lock_configuration_to_bucket(s3, bucket_name, lock_mode, retention_units, retention_length):
    object_lock_configuration=create_object_lock_configuration(lock_mode, retention_units, retention_length)
    result=True
    try:
        s3.put_object_lock_configuration(
            Bucket=bucket_name,
            ObjectLockConfiguration=object_lock_configuration
        )
        print(f"Lock configuration applied to bucket '{bucket_name}'.")
    except Exception as e:
        print(f"Error applying lock configuration to bucket '{bucket_name}': {e}")
        result=False
    return result

def upload_file_to_bucket(s3, bucket_name, file_name, file_path):
    # Upload file to bucket
    with open(file_path, 'rb') as f:
        s3.put_object(Bucket=bucket_name, Key=file_name, Body=f)
    
    print(f"Object '{file_path}' uploaded to bucket '{bucket_name}'.")

def create_buckets_with_locks_and_upload_files(access_key_id, secret_access_key, session_token):
    # Read JSON config file
    config_file="config.json"
    with open(config_file, 'r') as f:
        config_json = json.load(f)

    # ... and extract information
    region_name = config_json['Region']
    bucket_base_name = config_json['BucketBaseName']
    object_upload_directory = config_json['ObjectUploadDirectory']

    # Verify object upload directory exists
    if not os.path.exists(object_upload_directory):
        print(f"The object upload directory '{object_upload_directory}' does not exist.")
        return

    # Initialize AWS S3 client
    s3 = {}
    if session_token is None:
        s3 = boto3.client(
            's3',
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region_name
        )
    else:
        s3 = boto3.client(
            's3',
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            aws_session_token=session_token,
            region_name=region_name
        )

    # Create unique bucket name
    governance_bucket_unique_name = generate_bucket_unique_name(bucket_base_name, "governance")
    compliance_bucket_unique_name = generate_bucket_unique_name(bucket_base_name, "compliance")

    # debug
    print(f"region_name={region_name}")
    print(f"governance_bucket_unique_name={governance_bucket_unique_name}")
    print(f"compliance_bucket_unique_name={compliance_bucket_unique_name}")

    # Create governance bucket
    s3.create_bucket(
        Bucket=governance_bucket_unique_name
    )
    print(f"Bucket '{governance_bucket_unique_name}' created for writable objects.")
    if not enable_versioning(s3, governance_bucket_unique_name):
        return False
    # if not apply_lock_configuration_to_bucket(s3, governance_bucket_unique_name, 'GOVERNANCE', 'Days', 30):
    #     return False

    # Create compliance bucket
    s3.create_bucket(
        Bucket=compliance_bucket_unique_name
    )
    print(f"Bucket '{compliance_bucket_unique_name}' created for read-only objects.")
    if not enable_versioning(s3, compliance_bucket_unique_name):
        return False
    # if not apply_lock_configuration_to_bucket(s3, compliance_bucket_unique_name, 'COMPLIANCE', 'Years', 10):
    #     return False

    # Upload files to buckets based on write attribute
    for file_name in os.listdir(object_upload_directory):
        file_path = os.path.join(object_upload_directory, file_name)
        if os.path.isfile(file_path):
            if os.access(file_path, os.W_OK):
                upload_file_to_bucket(s3, governance_bucket_unique_name, file_name, file_path)
            else:
                upload_file_to_bucket(s3, compliance_bucket_unique_name, file_name, file_path)

    # Success
    return True

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python script.py <access_key_id> <secret_access_key> <session_token>")
        sys.exit(1)

    access_key_id = sys.argv[1]
    secret_access_key = sys.argv[2]
    session_token = sys.argv[3]
    if session_token == "None":
        session_token = None

    if create_buckets_with_locks_and_upload_files(access_key_id, secret_access_key, session_token):
        print("SUCCESS")
    else:
        print("FAILURE")
