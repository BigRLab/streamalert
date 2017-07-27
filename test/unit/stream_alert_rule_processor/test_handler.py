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
import base64
import logging

from mock import call, mock_open, patch

from nose.tools import (
    assert_equal,
    assert_false,
    assert_list_equal,
    assert_true,
    raises
)

from stream_alert.rule_processor import LOGGER
from stream_alert.rule_processor.config import ConfigError
from stream_alert.rule_processor.handler import StreamAlert
from stream_alert.rule_processor.handler import load_config


from unit.stream_alert_rule_processor.test_helpers import (
    _get_mock_context,
    _get_valid_event
)


@patch('stream_alert.rule_processor.handler.put_metric_data', lambda a, b, c: None)
class TestStreamAlert(object):
    """Test class for StreamAlert class"""
    @classmethod
    @patch('stream_alert.rule_processor.handler.load_config',
           lambda: load_config('test/unit/conf/'))
    def setup_class(cls):
        """Setup the class before any methods"""
        cls.__sa_handler = StreamAlert(_get_mock_context(), False)

    @classmethod
    def teardown_class(cls):
        """Teardown the class after all methods"""
        cls.__sa_handler = None

    def teardown(self):
        """Teardown the class after each methods"""
        del self.__sa_handler.alerts[:]
        self.__sa_handler.send_alerts = False

    def test_run_no_records(self):
        """StreamAlert Class - Run, No Records"""
        passed = self.__sa_handler.run({'Records': []})
        assert_false(passed)

    @staticmethod
    @raises(ConfigError)
    def test_run_config_error(_):
        """StreamAlert Class - Run, Config Error"""
        mock = mock_open(read_data='non-json string that will raise an exception')
        with patch('__builtin__.open', mock):
            StreamAlert(_get_mock_context(), False)

    def test_get_alerts(self):
        """StreamAlert Class - Get Alerts"""
        default_list = ['alert1', 'alert2']
        self.__sa_handler.alerts = default_list

        assert_list_equal(self.__sa_handler.get_alerts(), default_list)

    @patch('stream_alert.rule_processor.handler.StreamClassifier.load_sources')
    @patch('stream_alert.rule_processor.handler.StreamClassifier.extract_service_and_entity')
    def test_run_no_sources(self, extract_mock, load_sources_mock):
        """StreamAlert Class - Run, No Loaded Sources"""
        extract_mock.return_value = ('lambda', 'entity')
        load_sources_mock.return_value = None

        self.__sa_handler.run({'Records': ['record']})

        load_sources_mock.assert_called_with('lambda', 'entity')

    @patch('logging.Logger.error')
    @patch('stream_alert.rule_processor.handler.StreamClassifier.extract_service_and_entity')
    def test_run_bad_service(self, extract_mock, log_mock):
        """StreamAlert Class - Run, Bad Service"""
        extract_mock.return_value = ('', 'entity')

        self.__sa_handler.run({'Records': ['record']})

        log_mock.assert_any_call('No valid service found in payload\'s raw record')

    @patch('logging.Logger.error')
    @patch('stream_alert.rule_processor.handler.StreamClassifier.extract_service_and_entity')
    def test_run_bad_entity(self, extract_mock, log_mock):
        """StreamAlert Class - Run, Bad Entity"""
        extract_mock.return_value = ('kinesis', '')

        self.__sa_handler.run({'Records': ['record']})

        log_mock.assert_called_with(
            'Unable to map entity from payload\'s raw record for service %s',
            'kinesis'
        )

    @patch('stream_alert.rule_processor.handler.load_stream_payload')
    @patch('stream_alert.rule_processor.handler.StreamClassifier.load_sources')
    @patch('stream_alert.rule_processor.handler.StreamClassifier.extract_service_and_entity')
    def test_run_load_payload_bad(self, extract_mock, load_sources_mock, load_payload_mock):
        """StreamAlert Class - Run, Loaded Payload Fail"""
        extract_mock.return_value = ('lambda', 'entity')
        load_sources_mock.return_value = True

        self.__sa_handler.run({'Records': ['record']})

        load_payload_mock.assert_called_with('lambda', 'entity', 'record')

    @patch('stream_alert.rule_processor.handler.StreamRules.process')
    @patch('stream_alert.rule_processor.handler.StreamClassifier.extract_service_and_entity')
    def test_run_with_alert(self, extract_mock, rules_mock):
        """StreamAlert Class - Run, With Alert"""
        extract_mock.return_value = ('kinesis', 'unit_test_default_stream')
        rules_mock.return_value = ['success!!']

        passed = self.__sa_handler.run(_get_valid_event())

        assert_true(passed)

    @patch('logging.Logger.debug')
    @patch('stream_alert.rule_processor.handler.StreamClassifier.extract_service_and_entity')
    def test_run_no_alerts(self, extract_mock, log_mock):
        """StreamAlert Class - Run, With No Alerts"""
        extract_mock.return_value = ('kinesis', 'unit_test_default_stream')
        self.__sa_handler.run(_get_valid_event())

        calls = [call('Valid data, no alerts'),
                 call('Invalid log failure count: %d', 0),
                 call('%s alerts triggered', 0)]

        log_mock.assert_has_calls(calls)

    @patch('logging.Logger.error')
    @patch('stream_alert.rule_processor.handler.StreamClassifier.extract_service_and_entity')
    def test_run_invalid_data(self, extract_mock, log_mock):
        """StreamAlert Class - Run, Invalid Data"""
        extract_mock.return_value = ('kinesis', 'unit_test_default_stream')
        event = _get_valid_event()

        # Replace the good log data with bad data
        event['Records'][0]['kinesis']['data'] = base64.b64encode('{"bad": "data"}')
        self.__sa_handler.run(event)

        assert_equal(log_mock.call_args[0][0], 'Invalid data: %s\n%s')
        assert_equal(log_mock.call_args[0][2], '{"bad": "data"}')

    @patch('stream_alert.rule_processor.sink.StreamSink.sink')
    @patch('stream_alert.rule_processor.handler.StreamRules.process')
    @patch('stream_alert.rule_processor.handler.StreamClassifier.extract_service_and_entity')
    def test_run_send_alerts(self, extract_mock, rules_mock, sink_mock):
        """StreamAlert Class - Run, Send Alert"""
        extract_mock.return_value = ('kinesis', 'unit_test_default_stream')
        rules_mock.return_value = ['success!!']

        # Set send_alerts to true so the sink happens
        self.__sa_handler.send_alerts = True

        self.__sa_handler.run(_get_valid_event())

        sink_mock.assert_called_with(['success!!'])

    @patch('logging.Logger.debug')
    @patch('stream_alert.rule_processor.handler.StreamRules.process')
    @patch('stream_alert.rule_processor.handler.StreamClassifier.extract_service_and_entity')
    def test_run_debug_log_alert(self, extract_mock, rules_mock, log_mock):
        """StreamAlert Class - Run, Debug Log Alert"""
        extract_mock.return_value = ('kinesis', 'unit_test_default_stream')
        rules_mock.return_value = ['success!!']

        # Cache the logger level
        lvl = LOGGER.getEffectiveLevel()

        # Increase the logger level to debug
        LOGGER.setLevel(logging.DEBUG)

        self.__sa_handler.run(_get_valid_event())

        # Reset the logger level
        LOGGER.setLevel(lvl)

        log_mock.assert_called_with('Alerts:\n%s', '[\n  "success!!"\n]')

    @patch('stream_alert.rule_processor.handler.load_stream_payload')
    @patch('stream_alert.rule_processor.handler.StreamClassifier.load_sources')
    @patch('stream_alert.rule_processor.handler.StreamClassifier.extract_service_and_entity')
    def test_run_no_payload_class(self, extract_mock, load_sources_mock, load_payload_mock):
        """StreamAlert Class - Run, No Payload Class"""
        extract_mock.return_value = ('blah', 'entity')
        load_sources_mock.return_value = True
        load_payload_mock.return_value = None

        self.__sa_handler.run({'Records': ['record']})

        load_payload_mock.assert_called()
