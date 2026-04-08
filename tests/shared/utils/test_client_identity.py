from shared.product_constants import PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_WHITELIST
from shared.utils.client_identity import (
    build_generated_client_label,
    build_vpn_client_email,
    normalize_client_identity_seed,
)


def test_normalize_client_identity_seed_uses_local_part_and_slugifies():
    assert normalize_client_identity_seed("Alice+QA@example.com") == "alice-qa"


def test_build_generated_client_label_includes_seed_when_present():
    assert (
        build_generated_client_label(
            seed="remote_access_support",
            generated_value="bold-union-6aa5f0f9",
        )
        == "remote_access_support-bold-union-6aa5f0f9"
    )


def test_build_generated_client_label_uses_generated_value_without_seed():
    assert build_generated_client_label(seed=None, generated_value="mail.test") == "mail-test"


def test_build_vpn_client_email_uses_consistent_standard_format():
    assert (
        build_vpn_client_email(
            seed="Alice+QA@example.com",
            client_uuid="653c35c9-e892-404b-953c-416dcef35fd1",
            scope=PRODUCT_SCOPE_STANDARD,
        )
        == "alice-qa-653c35c9"
    )


def test_build_vpn_client_email_uses_consistent_whitelist_format():
    assert (
        build_vpn_client_email(
            seed="Alice+QA@example.com",
            client_uuid="ca0968d4-1eed-40df-bec7-bdd33416c270",
            scope=PRODUCT_SCOPE_WHITELIST,
        )
        == "wl-alice-qa-ca0968d4"
    )
