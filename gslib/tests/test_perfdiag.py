# -*- coding: utf-8 -*-
# Copyright 2013 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Integration tests for perfdiag command."""

from __future__ import absolute_import

import os
import socket

import boto

import gslib.tests.testcase as testcase
from gslib.tests.util import ObjectToURI as suri
from gslib.tests.util import RUN_S3_TESTS
from gslib.tests.util import unittest
from gslib.util import IS_WINDOWS


class TestPerfDiag(testcase.GsUtilIntegrationTestCase):
  """Integration tests for perfdiag command."""

  # We want to test that perfdiag works both when connecting to the standard gs
  # endpoint, and when connecting to a specific IP or host while setting the
  # host header. For the 2nd case we resolve gs_host (normally
  # storage.googleapis.com) to a specific IP and connect to that explicitly.
  _gs_host = boto.config.get(
      'Credentials', 'gs_host', boto.gs.connection.GSConnection.DefaultHost)
  _gs_ip = socket.gethostbyname(_gs_host)
  _custom_endpoint_flags = [
      '-o', 'Credentials:gs_host=' + _gs_ip,
      '-o', 'Credentials:gs_host_header=' + _gs_host,
      # TODO: gsutil-beta: Add host header support for JSON
      '-o', 'Boto:https_validate_certificates=False']

  def _should_run_with_custom_endpoints(self):
    # Host headers are only supported for XML, and not when
    # using environment variables for proxies.
    return self.test_api == 'XML' and not (os.environ.get('http_proxy') or
                                           os.environ.get('https_proxy') or
                                           os.environ.get('HTTPS_PROXY'))

  def test_latency(self):
    bucket_uri = self.CreateBucket()
    cmd = ['perfdiag', '-n', '1', '-t', 'lat', suri(bucket_uri)]
    self.RunGsUtil(cmd)
    if self._should_run_with_custom_endpoints():
      self.RunGsUtil(self._custom_endpoint_flags + cmd)
    self.AssertNObjectsInBucket(bucket_uri, 0, versioned=True)

  def _run_throughput_test(self, test_name, num_processes, num_threads,
                           parallelism_strategy=None):
    bucket_uri = self.CreateBucket()

    cmd = ['perfdiag', '-n', str(num_processes * num_threads),
           '-s', '1024', '-c', str(num_processes), '-k', str(num_threads),
           '-t', test_name]
    if parallelism_strategy:
      cmd += ['-p', parallelism_strategy]
    cmd += [suri(bucket_uri)]

    self.RunGsUtil(cmd)
    if self._should_run_with_custom_endpoints():
      self.RunGsUtil(self._custom_endpoint_flags + cmd)
    self.AssertNObjectsInBucket(bucket_uri, 0, versioned=True)

  def _run_each_parallel_throughput_test(self, test_name, num_processes,
                                         num_threads):
    self._run_throughput_test(test_name, num_processes, num_threads, 'fan')
    if RUN_S3_TESTS and test_name in ('wthru', 'wthru_file'):
      # Sliced uploads are not available for s3.
      pass
    else:
      self._run_throughput_test(test_name, num_processes, num_threads, 'slice')
      self._run_throughput_test(test_name, num_processes, num_threads, 'both')

  def test_write_throughput_single_process_single_thread(self):
    self._run_throughput_test('wthru', 1, 1)
    self._run_throughput_test('wthru_file', 1, 1)

  def test_write_throughput_single_process_multi_thread(self):
    self._run_each_parallel_throughput_test('wthru', 1, 2)
    self._run_each_parallel_throughput_test('wthru_file', 1, 2)

  @unittest.skipIf(IS_WINDOWS, 'Multiprocessing is not supported on Windows')
  def test_write_throughput_multi_process_single_thread(self):
    self._run_each_parallel_throughput_test('wthru', 2, 1)
    self._run_each_parallel_throughput_test('wthru_file', 2, 1)

  @unittest.skipIf(IS_WINDOWS, 'Multiprocessing is not supported on Windows')
  def test_write_throughput_multi_process_multi_thread(self):
    self._run_each_parallel_throughput_test('wthru', 2, 2)
    self._run_each_parallel_throughput_test('wthru_file', 2, 2)

  def test_read_throughput_single_process_single_thread(self):
    self._run_throughput_test('rthru', 1, 1)
    self._run_throughput_test('rthru_file', 1, 1)

  def test_read_throughput_single_process_multi_thread(self):
    self._run_each_parallel_throughput_test('rthru', 1, 2)
    self._run_each_parallel_throughput_test('rthru_file', 1, 2)

  @unittest.skipIf(IS_WINDOWS, 'Multiprocessing is not supported on Windows')
  def test_read_throughput_multi_process_single_thread(self):
    self._run_each_parallel_throughput_test('rthru', 2, 1)
    self._run_each_parallel_throughput_test('rthru_file', 2, 1)

  @unittest.skipIf(IS_WINDOWS, 'Multiprocessing is not supported on Windows')
  def test_read_throughput_multi_process_multi_thread(self):
    self._run_each_parallel_throughput_test('rthru', 2, 2)
    self._run_each_parallel_throughput_test('rthru_file', 2, 2)

  def test_input_output(self):
    outpath = self.CreateTempFile()
    bucket_uri = self.CreateBucket()
    self.RunGsUtil(['perfdiag', '-o', outpath, '-n', '1', '-t', 'lat',
                    suri(bucket_uri)])
    self.RunGsUtil(['perfdiag', '-i', outpath])

  def test_invalid_size(self):
    stderr = self.RunGsUtil(
        ['perfdiag', '-n', '1', '-s', 'foo', '-t', 'wthru', 'gs://foobar'],
        expected_status=1, return_stderr=True)
    self.assertIn('Invalid -s', stderr)

  def test_toobig_size(self):
    stderr = self.RunGsUtil(
        ['perfdiag', '-n', '1', '-s', '3pb', '-t', 'wthru', 'gs://foobar'],
        expected_status=1, return_stderr=True)
    self.assertIn('in-memory tests maximum file size', stderr)

  def test_listing(self):
    bucket_uri = self.CreateBucket()
    stdout = self.RunGsUtil(
        ['perfdiag', '-n', '1', '-t', 'list', suri(bucket_uri)],
        return_stdout=True)
    self.assertIn('Number of listing calls made:', stdout)
    self.AssertNObjectsInBucket(bucket_uri, 0, versioned=True)
