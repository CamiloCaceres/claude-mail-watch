"""Tests for the standalone watcher's trust rules. Run: python3 -m unittest discover watcher"""

import email
import email.policy
import os
import tempfile
import unittest

import mail_watch


def message(sender: str, *auth_results: str, body: str = "hello") -> email.message.Message:
    lines = [f"Authentication-Results: {a}" for a in auth_results]
    raw = "\n".join([*lines, f"From: {sender}", "Subject: hi", "", body])
    return email.message_from_string(raw, policy=email.policy.default)


TRUSTED = ["boss@example.com"]


class Trust(unittest.TestCase):
    def test_dmarc_pass_from_trusted_sender_is_trusted(self):
        msg = message("Boss <boss@example.com>", "mx.host; dkim=pass header.d=example.com; spf=pass; dmarc=pass")
        self.assertEqual(mail_watch.classify(msg, TRUSTED)["trust"], "trusted")

    def test_aligned_dkim_without_dmarc_is_trusted(self):
        msg = message("boss@example.com", "mx.host; dkim=pass header.d=mail.example.com")
        self.assertEqual(mail_watch.classify(msg, TRUSTED)["trust"], "trusted")

    def test_dkim_pass_for_another_domain_is_spoofed(self):
        msg = message("boss@example.com", "mx.host; dkim=pass header.d=evil.test; spf=pass smtp.mailfrom=x@evil.test")
        self.assertEqual(mail_watch.classify(msg, TRUSTED)["trust"], "spoofed")

    def test_no_auth_header_is_spoofed(self):
        self.assertEqual(mail_watch.classify(message("boss@example.com"), TRUSTED)["trust"], "spoofed")

    def test_only_the_topmost_auth_header_counts(self):
        # The forged pass sits below the receiving server's fail, so it is ignored.
        msg = message("boss@example.com", "mx.host; dmarc=fail", "forger; dmarc=pass")
        self.assertEqual(mail_watch.classify(msg, TRUSTED)["trust"], "spoofed")

    def test_unknown_sender_is_external_even_when_authenticated(self):
        msg = message("someone@else.test", "mx.host; dmarc=pass")
        self.assertEqual(mail_watch.classify(msg, TRUSTED)["trust"], "external")

    def test_address_match_ignores_case_and_display_name(self):
        msg = message('"The Boss" <BOSS@Example.com>', "mx.host; dmarc=pass")
        self.assertEqual(mail_watch.classify(msg, TRUSTED)["trust"], "trusted")


class Body(unittest.TestCase):
    def test_html_only_mail_becomes_text(self):
        raw = "Content-Type: text/html\n\n<p>Deploy <b>now</b></p><script>x()</script>"
        msg = email.message_from_string(raw, policy=email.policy.default)
        self.assertEqual(mail_watch.body_text(msg, 100), "Deploy now")

    def test_long_bodies_are_cut(self):
        text = mail_watch.body_text(message("a@b.c", body="x" * 50), 10)
        self.assertTrue(text.startswith("x" * 10) and text.endswith("[... cut]"))


class Password(unittest.TestCase):
    def test_environment_wins_over_dotenv(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
            handle.write("# comment\nexport MW_TEST_PW='from-file'\n")
        try:
            self.assertEqual(mail_watch.password_from("MW_TEST_PW", handle.name), "from-file")
            os.environ["MW_TEST_PW"] = "from-env"
            self.assertEqual(mail_watch.password_from("MW_TEST_PW", handle.name), "from-env")
        finally:
            os.environ.pop("MW_TEST_PW", None)
            os.unlink(handle.name)

    def test_missing_password_is_reported_not_raised(self):
        args = mail_watch.argparse.Namespace(password_env="MW_NOPE", dotenv=None, user="a@b.c")
        self.assertIn("no password", mail_watch.watch(args)["error"])


if __name__ == "__main__":
    unittest.main()
