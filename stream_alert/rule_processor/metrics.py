'''
Copyright 2017-present, Airbnb Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
'''
import json

import boto3

from datetime import datetime

from botocore.exceptions import ClientError

from stream_alert.rule_processor import LOGGER


BOTO_CW_CLIENT = boto3.client('cloudwatch')

class Metrics(object):
    """Class to hold Rule Processor metric name and unit constants"""
    class Name(object):
        """Constant metric names used in the rule processor"""
        FAILED_PARSES = 'RuleProcessorFailedParses'
        S3_DOWNLOAD_TIME = 'RuleProcessorS3DownloadTime'
        TOTAL_RECORDS = 'RuleProcessorTotalRecords'
        TOTAL_S3_RECORDS = 'RuleProcessorTotalS3Records'
        TOTAL_SNS_RECORDS = 'RuleProcessorTotalSNSRecords'
        TOTAL_KINESIS_RECORDS = 'RuleProcessorTotalKinesisRecords'
        TRIGGERED_ALERTS = 'RuleProcessorTriggeredAlerts'

    class Unit(object):
        """Unit names for metrics"""
        SECONDS = 'Seconds'
        MICROSECONDS = 'Microseconds'
        MILLISECONDS = 'Milliseconds'
        BYTES = 'Bytes'
        KILOBYTES = 'Kilobytes'
        MEGABYTES = 'Megabytes'
        GIGABYTES = 'Gigabytes'
        TERABYTES = 'Terabytes'
        BITS = 'Bits'
        KILOBITS = 'Kilobits'
        MEGABITS = 'Megabits'
        GIGABITS = 'Gigabits'
        TERABITS = 'Terabits'
        PERCENT = 'Percent'
        COUNT = 'Count'
        BYTES_PER_SECOND = 'Bytes/Second'
        KILOBYTES_PER_SECOND = 'Kilobytes/Second'
        MEGABYTES_PER_SECOND = 'Megabytes/Second'
        GIGABYTES_PER_SECOND = 'Gigabytes/Second'
        TERABYTES_PER_SECOND = 'Terabytes/Second'
        BITS_PER_SECOND = 'Bits/Second'
        KILOBITS_PER_SECOND = 'Kilobits/Second'
        MEGABITS_PER_SECOND = 'Megabits/Second'
        GIGABITS_PER_SECOND = 'Gigabits/Second'
        TERABITS_PER_SECOND = 'Terabits/Second'
        COUNT_PER_SECOND = 'Count/Second'
        NONE = 'None'


def put_metric_data(metric_name, value, unit):
    """Publish custom metric data to CloudWatch.

    Args:
        metric_name [string]: Name of metric to publish to
        value [number]: Numeric information to post to metric. AWS expects
            this to be of type 'float' but will accept any numeric value that
            is not super small (negative) or super large.
        unit [string]: Unit to use for this metric. Choices are in Metrics above.
    """
    if metric_name not in Metrics.Name.__dict__.values():
        LOGGER.error('Metric name not defined: %s', metric_name)
        return

    if unit not in Metrics.Unit.__dict__.values():
        LOGGER.error('Metric unit not defined: %s', unit)
        return

    LOGGER.debug('Sending metric data to CloudWatch: %s', metric_name)
    metric_data = [
        {
            'MetricName': metric_name,
            'Timestamp': datetime.utcnow(),
            'Unit': unit,
            'Value': value
        }
    ]

    _put_metric(metric_data)


def _put_metric(data):
    """Helper function to publish custom metric data for StreamAlert to CloudWatch

    Args:
        data [list<dict>] a list of dictionary items to publish that conforms to
            the format expected by CloudWatch
    """
    try:
        BOTO_CW_CLIENT.put_metric_data(Namespace='StreamAlert', MetricData=data)
    except ClientError as err:
        LOGGER.exception('Failed to send metric to CloudWatch. Error: %s\nMetric:\n%s',
                         err.response, json.dumps(data, indent=2))
