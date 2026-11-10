import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == 'posix' and shutil.which('bash'), 'Linux shell behavior is tested by Actions')
class DeploymentCommands(unittest.TestCase):
    def run_deploy(self, status, revision='a' * 40, promoted_revision=None,
                   digest='sha256:' + '1' * 64):
        with tempfile.TemporaryDirectory() as directory:
            fake_aws = Path(directory) / 'aws'
            fake_aws.write_text('#!/bin/sh\n'
                'echo "$*" >> "$CALLS_FILE"\n'
                'case "$*" in\n'
                '*send-command*) echo "00000000-0000-0000-0000-000000000001" ;;\n'
                '*get-command-invocation*) printf \'{"Status":"%s","Code":0}\\n\' "$FAKE_STATUS" ;;\n'
                '*) exit 9 ;;\nesac\n')
            fake_aws.chmod(0o755)
            calls = Path(directory) / 'calls'
            env = {**os.environ, 'PATH': directory + os.pathsep + os.environ['PATH'],
                'DEPLOY_INSTANCE_ID': 'i-test', 'DEPLOY_DOCUMENT': 'test-deploy',
                'DEPLOY_IMAGE_DIGEST': digest, 'GITHUB_SHA': revision,
                'FAKE_STATUS': status, 'CALLS_FILE': str(calls)}
            if promoted_revision is not None:
                env['DEPLOY_REVISION'] = promoted_revision
            result = subprocess.run(['bash', str(ROOT / 'ci/deploy.sh')], env=env,
                capture_output=True, text=True, timeout=15)
            return result, calls.read_text() if calls.exists() else ''

    def test_success_waits_for_successful_command(self):
        result, calls = self.run_deploy('Success')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--document-name test-deploy', calls)
        self.assertIn('--instance-ids i-test', calls)
        self.assertIn('imageDigest', calls)
        self.assertIn('sha256:' + '1' * 64, calls)
        self.assertIn('get-command-invocation', calls)

    def test_failure_is_reported_without_retrying_or_recovery(self):
        result, calls = self.run_deploy('Failed')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls.count('send-command'), 1)
        self.assertEqual(calls.count('get-command-invocation'), 1)
        self.assertNotIn('restart', calls)

    def test_invalid_revision_is_rejected_before_any_aws_operation(self):
        result, calls = self.run_deploy('Success', 'main; echo unsafe')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, '')

    def test_invalid_digest_is_rejected_before_any_aws_operation(self):
        result, calls = self.run_deploy('Success', digest='sha256:unsafe')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, '')

    def test_promoted_revision_overrides_workflow_revision(self):
        promoted = 'b' * 40
        result, calls = self.run_deploy('Success', revision='a' * 40, promoted_revision=promoted)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(promoted, calls)
        self.assertNotIn('a' * 40, calls)


class ProductionPromotionWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / '.github/workflows/promote-production.yml').read_text()

    def test_manual_verified_development_revision_is_used(self):
        self.assertIn('workflow_dispatch:', self.workflow)
        self.assertIn('/health/ready', self.workflow)
        self.assertIn('actions/workflows/ci.yml/runs', self.workflow)
        self.assertIn('conclusion', self.workflow)
        self.assertIn('deployment-manifest', self.workflow)
        self.assertIn('DEPLOY_IMAGE_DIGEST: ${{ needs.select-revision.outputs.digest }}', self.workflow)
        self.assertIn('DEPLOY_REVISION: ${{ needs.select-revision.outputs.revision }}', self.workflow)
        self.assertNotIn('DEPLOY_REVISION: ${{ github.sha }}', self.workflow)

    def test_production_is_serialized_and_environment_scoped(self):
        self.assertIn('group: blueprint-production-promotion', self.workflow)
        self.assertIn('cancel-in-progress: false', self.workflow)
        self.assertIn('environment: production', self.workflow)
        self.assertIn('id-token: write', self.workflow)
        self.assertIn('test "$DEPLOY_INSTANCE_ID" = "i-088ca3bcb29814cef"', self.workflow)


class ImmutableImagePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ci = (ROOT / '.github/workflows/ci.yml').read_text()
        cls.rollback = (ROOT / '.github/workflows/rollback-production.yml').read_text()
        cls.document = (ROOT / 'deploy/aws/github-oidc-stack.yaml').read_text()
        cls.registry = (ROOT / 'deploy/aws/ecr-stack.yaml').read_text()

    def test_ci_publishes_tagged_digest_after_tests(self):
        self.assertIn('needs: [stack]', self.ci)
        self.assertIn('bash ci/build_and_push.sh', self.ci)
        self.assertIn('deployment-manifest', self.ci)
        script = (ROOT / 'ci/build_and_push.sh').read_text()
        self.assertIn('date -u +%Y%m%d-%H%M%S', script)
        self.assertIn('imageDigest', script)

    def test_host_pulls_digest_without_building(self):
        self.assertIn('docker pull "$image_ref"', self.document)
        self.assertIn('up -d --no-build --no-deps', self.document)
        self.assertNotIn('docker compose -f docker-compose.aws.yaml build', self.document)

    def test_repository_and_rollback_are_immutable_and_protected(self):
        self.assertIn('ImageTagMutability: IMMUTABLE', self.registry)
        self.assertIn('DeletionPolicy: Retain', self.registry)
        self.assertIn('UpdateReplacePolicy: Retain', self.registry)
        self.assertIn('environment: production', self.rollback)
        self.assertIn('deployment-manifest', self.rollback)
        self.assertIn('group: blueprint-production-promotion', self.rollback)
