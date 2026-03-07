from django.test import SimpleTestCase

from gardn.settings import _get_staticfiles_backend


class StaticStorageTests(SimpleTestCase):
    def test_uses_s3_when_configured(self):
        self.assertEqual(
            _get_staticfiles_backend("my-bucket"),
            "storages.backends.s3boto3.S3StaticStorage",
        )

    def test_falls_back_to_whitenoise(self):
        self.assertEqual(
            _get_staticfiles_backend(""),
            "whitenoise.storage.CompressedManifestStaticFilesStorage",
        )
