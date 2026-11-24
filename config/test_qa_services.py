from pathlib import Path
from unittest.mock import patch

from django.core.management import CommandError
from django.test import SimpleTestCase

from config.management.commands.importar_laravel import Command
from pipeline_multimodal.servicios import ErrorPipelineMultimodal, ServicioPipelineMultimodal


class ServiceIsolationTests(SimpleTestCase):
    def test_importer_rejects_unknown_table_before_query(self):
        with self.assertRaises(CommandError):
            Command()._query_remote_db(object(), "usuarios; DROP TABLE users")

    def test_importer_uses_argv_and_quotes_remote_command(self):
        command = Command()
        connection = {
            "ssh": True,
            "host": "db.example; touch /tmp/pwned",
            "user": "legacy user",
            "password": "secret; echo unsafe",
            "database": "legacy-db",
        }
        completed = type("Completed", (), {"returncode": 0, "stdout": "1\tAna\n", "stderr": ""})()
        with patch("subprocess.run", return_value=completed) as run:
            result = command._query_remote_db(connection, "usuarios")

        self.assertEqual(result, [["1", "Ana"]])
        argv = run.call_args.args[0]
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(argv[:2], ["sshpass", "-e"])
        self.assertIn("touch /tmp/pwned", argv[-2])
        self.assertIn("'MYSQL_PWD=secret; echo unsafe'", argv[-1])
        self.assertEqual(run.call_args.kwargs["env"]["SSHPASS"], connection["password"])

    def test_multimodal_service_rejects_invalid_process_contract(self):
        service = ServicioPipelineMultimodal(Path("/project"), Path("/usr/bin/python"), timeout=3)
        completed = type("Completed", (), {"returncode": 0, "stdout": "{}", "stderr": ""})()
        with patch("pipeline_multimodal.servicios.subprocess.run", return_value=completed):
            with self.assertRaises(ErrorPipelineMultimodal):
                service.ejecutar(Path("/tmp/video.mp4"), "SESSION-001")
