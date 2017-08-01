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

from mock import call, patch

from nose.tools import (
    assert_equal,
    assert_false,
    assert_is_instance,
    assert_list_equal,
    assert_true
)

import stream_alert.rule_processor.classifier as sa_classifier
# from stream_alert.rule_processor.classifier import StreamClassifier
from stream_alert.rule_processor.config import load_config
from stream_alert.rule_processor.payload import load_stream_payload

from unit.stream_alert_rule_processor.test_helpers import (
    _make_kinesis_raw_record
)


class TestStreamClassifier(object):
    """Test class for StreamClassifier"""
    @classmethod
    def setup_class(cls):
        """Setup the class before any methods"""
        config = load_config('test/unit/conf')
        cls.classifier = sa_classifier.StreamClassifier(config)

    @classmethod
    def teardown_class(cls):
        """Teardown the class after all methods"""
        cls.classifier = None

    def teardown(self):
        """Teardown after each method"""
        del self.classifier._entity_log_sources[:]
        sa_classifier.SUPPORT_MULTIPLE_SCHEMA_MATCHING = False

    def test_convert_type_string(self):
        """StreamClassifier - Convert Type, Default String"""
        payload = {'key_01': 10.101}
        schema = {'key_01': 'string'}

        self.classifier._convert_type(payload, schema)

        assert_is_instance(payload['key_01'], str)
        assert_equal(payload['key_01'], '10.101')

    def test_convert_type_valid_int(self):
        """StreamClassifier - Convert Type, Valid Int"""
        payload = {'key_01': '100'}
        schema = {'key_01': 'integer'}

        self.classifier._convert_type(payload, schema)

        assert_is_instance(payload['key_01'], int)

    @patch('logging.Logger.error')
    def test_convert_type_invalid_int(self, log_mock):
        """StreamClassifier - Convert Type, Invalid Int"""
        payload = {'key_01': 'NotInt'}
        schema = {'key_01': 'integer'}

        self.classifier._convert_type(payload, schema)

        log_mock.assert_called_with(
            'Invalid schema. Value for key [%s] is not an int: %s',
            'key_01',
            'NotInt')

    def test_convert_type_valid_float(self):
        """StreamClassifier - Convert Type, Valid Float"""
        payload = {'key_01': '12.1'}
        schema = {'key_01': 'float'}

        self.classifier._convert_type(payload, schema)

        assert_is_instance(payload['key_01'], float)

    @patch('logging.Logger.error')
    def test_convert_type_invalid_float(self, log_mock):
        """StreamClassifier - Convert Type, Invalid Float"""
        payload = {'key_01': 'NotFloat'}
        schema = {'key_01': 'float'}

        self.classifier._convert_type(payload, schema)

        log_mock.assert_called_with(
            'Invalid schema. Value for key [%s] is not a float: %s',
            'key_01',
            'NotFloat')

    @patch('logging.Logger.error')
    def test_convert_type_unsup_type(self, log_mock):
        """StreamClassifier - Convert Type, Unsupported Type"""
        payload = {'key_01': 'true'}
        schema = {'key_01': 'boopean'}

        self.classifier._convert_type(payload, schema)

        log_mock.assert_called_with('Unsupported schema type: %s', 'boopean')

    def test_convert_type_list(self):
        """StreamClassifier - Convert Type, Skip List"""
        payload = {'key_01': ['hi', '100']}
        schema = {'key_01': ['integer']}

        self.classifier._convert_type(payload, schema)

        # Make sure the list was not modified
        assert_list_equal(payload['key_01'], ['hi', '100'])

    def test_convert_recursion(self):
        """StreamClassifier - Convert Type, Recursive"""
        payload = {'key_01': {'nested_key_01': '20.1'}}
        schema = {'key_01': {'nested_key_01': 'float'}}

        self.classifier._convert_type(payload, schema)

        # Make sure the list was not modified
        assert_is_instance(payload['key_01']['nested_key_01'], float)

    def test_convert_cast_envelope(self):
        """StreamClassifier - Convert Type, Cast Envelope"""
        payload = {'key_01': '100', 'streamalert:envelope_keys': {'env': '200'}}
        schema = {'key_01': 'integer', 'streamalert:envelope_keys': {'env': 'integer'}}

        self.classifier._convert_type(payload, schema)

        # Make sure the list was not modified
        assert_is_instance(payload['streamalert:envelope_keys']['env'], int)

    def test_convert_skip_bad_envelope(self):
        """StreamClassifier - Convert Type, Skip Bad Envelope"""
        payload = {'key_01': '100', 'streamalert:envelope_keys': 'bad_value'}
        schema = {'key_01': 'integer', 'streamalert:envelope_keys': {'env': 'integer'}}

        self.classifier._convert_type(payload, schema)

        # Make sure the list was not modified
        assert_equal(payload['streamalert:envelope_keys'], 'bad_value')

    def test_service_entity_ext_kinesis(self):
        """StreamClassifier - Extract Service and Entity, Kinesis"""
        raw_record = {
            'kinesis': {
                'data': 'SGVsbG8sIHRoaXMgaXMgYSB0ZXN0IDEyMy4='
            },
            'eventSourceARN': 'arn:aws:kinesis:EXAMPLE/unit_test_stream_name'
        }

        service, entity = self.classifier.extract_service_and_entity(raw_record)

        assert_equal(service, 'kinesis')
        assert_equal(entity, 'unit_test_stream_name')

    def test_service_entity_ext_s3(self):
        """StreamClassifier - Extract Service and Entity, S3"""
        raw_record = {
            's3': {'bucket': {'name': 'unit_test_bucket'}}
        }

        service, entity = self.classifier.extract_service_and_entity(raw_record)

        assert_equal(service, 's3')
        assert_equal(entity, 'unit_test_bucket')

    def test_service_entity_ext_sns(self):
        """StreamClassifier - Extract Service and Entity, SNS"""
        raw_record = {
            'Sns': {'Message': 'test_message'},
            'EventSubscriptionArn': 'arn:aws:sns:us-east-1:123456789012:unit_test_topic'
        }

        service, entity = self.classifier.extract_service_and_entity(raw_record)

        assert_equal(service, 'sns')
        assert_equal(entity, 'unit_test_topic')

    def test_load_sources_valid(self):
        """StreamClassifier - Load Log Sources for Service and Entity, Valid"""
        service = 'kinesis'
        entity = 'unit_test_default_stream'

        result = self.classifier.load_sources(service, entity)

        assert_true(result)

        assert_equal(self.classifier._entity_log_sources[0], 'unit_test_simple_log')

    @patch('logging.Logger.error')
    def test_load_sources_invalid_serv(self, log_mock):
        """StreamClassifier - Load Log Sources for Service and Entity, Invalid Service"""
        service = 'kinesys'

        result = self.classifier.load_sources(service, '')

        assert_false(result)

        log_mock.assert_called_with('Service [%s] not declared in sources configuration',
                                    service)

    @patch('logging.Logger.error')
    def test_load_sources_invalid_ent(self, log_mock):
        """StreamClassifier - Load Log Sources for Service and Entity, Invalid Entity"""
        service = 'kinesis'
        entity = 'unit_test_bad_stream'

        result = self.classifier.load_sources(service, entity)

        assert_false(result)

        log_mock.assert_called_with(
            'Entity [%s] not declared in sources configuration for service [%s]',
            entity,
            service
        )

    def test_get_log_info(self):
        """StreamClassifier - Load Log Info for Source"""
        self.classifier._entity_log_sources.append('unit_test_simple_log')

        logs = self.classifier.get_log_info_for_source()

        assert_list_equal(logs.keys(), ['unit_test_simple_log'])

    @patch('logging.Logger.error')
    def test_parse_convert_fail(self, log_mock):
        """StreamClassifier - Convert Failed"""
        service = 'kinesis'
        entity = 'unit_test_default_stream'

        result = self.classifier.load_sources(service, entity)

        assert_true(result)

        kinesis_data = json.dumps({
            'unit_key_01': 'not an integer',
            'unit_key_02': 'valid string'
        })

        raw_record = _make_kinesis_raw_record(entity, kinesis_data)
        payload = load_stream_payload(service, entity, raw_record, None)
        payload = payload.pre_parse().next()

        result = self.classifier._parse(payload)

        assert_false(result)

        log_mock.assert_called_with(
            'Invalid schema. Value for key [%s] is not an int: %s',
            'unit_key_01', 'not an integer'
        )

    def test_mult_schema_match_success(self):
        """StreamClassifier - Multiple Schema Matching with Log Patterns, Success"""
        kinesis_data = json.dumps({
            'name': 'file added test',
            'identifier': 'host4.this.test',
            'time': 'Jan 01 2017',
            'type': 'lol_file_added_event_test',
            'message': 'bad_001.txt was added'
        })
        # Make sure support for multiple schema matching is ON
        sa_classifier.SUPPORT_MULTIPLE_SCHEMA_MATCHING = True

        service = 'kinesis'
        entity = 'test_stream_2'
        raw_record = _make_kinesis_raw_record(entity, kinesis_data)
        payload = load_stream_payload(service, entity, raw_record, None)

        self.classifier.load_sources(service, entity)

        payload = payload.pre_parse().next()

        valid_parses = self.classifier._process_log_schemas(payload)

        assert_equal(len(valid_parses), 2)
        assert_equal(valid_parses[0].log_name, 'test_multiple_schemas:01')
        assert_equal(valid_parses[1].log_name, 'test_multiple_schemas:02')
        valid_parse = self.classifier._check_valid_parse(valid_parses)

        assert_equal(valid_parse.log_name, 'test_multiple_schemas:01')

    @patch('logging.Logger.error')
    def test_mult_schema_match_failure(self, log_mock):
        """StreamClassifier - Multiple Schema Matching with Log Patterns, Fail"""
        kinesis_data = json.dumps({
            'name': 'file removal test',
            'identifier': 'host4.this.test.also',
            'time': 'Jan 01 2017',
            'type': 'file_removed_event_test_file_added_event',
            'message': 'bad_001.txt was removed'
        })
        sa_classifier.SUPPORT_MULTIPLE_SCHEMA_MATCHING = True

        service = 'kinesis'
        entity = 'test_stream_2'
        raw_record = _make_kinesis_raw_record(entity, kinesis_data)
        payload = load_stream_payload(service, entity, raw_record, None)

        self.classifier.load_sources(service, entity)

        payload = payload.pre_parse().next()

        valid_parses = self.classifier._process_log_schemas(payload)

        assert_equal(len(valid_parses), 2)
        self.classifier._check_valid_parse(valid_parses)

        log_mock.assert_called_with(
            'Proceeding with schema for: %s', 'test_multiple_schemas:01'
        )

    @patch('logging.Logger.error')
    def test_mult_schema_match(self, log_mock):
        """StreamClassifier - Multiple Schema Matching with Log Patterns"""
        kinesis_data = json.dumps({
            'name': 'file removal test',
            'identifier': 'host4.this.test.also',
            'time': 'Jan 01 2017',
            'type': 'random',
            'message': 'bad_001.txt was removed'
        })
        sa_classifier.SUPPORT_MULTIPLE_SCHEMA_MATCHING = True

        service = 'kinesis'
        entity = 'test_stream_2'
        raw_record = _make_kinesis_raw_record(entity, kinesis_data)
        payload = load_stream_payload(service, entity, raw_record, None)

        self.classifier.load_sources(service, entity)

        payload = payload.pre_parse().next()

        valid_parses = self.classifier._process_log_schemas(payload)

        assert_equal(len(valid_parses), 2)
        self.classifier._check_valid_parse(valid_parses)

        calls = [call('Log classification matched for multiple schemas: %s',
                      'test_multiple_schemas:01, test_multiple_schemas:02'),
                 call('Proceeding with schema for: %s', 'test_multiple_schemas:01')]

        log_mock.assert_has_calls(calls)
