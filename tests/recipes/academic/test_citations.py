"""Deterministic citation rules: identifiers, source status, the fabrication guard."""

from __future__ import annotations

import pytest

from crewforge.recipes.academic.citations import (
    analyse_draft,
    check_formatted,
    check_source,
    identifiers,
    isbn_valid,
    split_references,
)


class TestIdentifiers:
    def test_doi_plain_and_trailing_punctuation(self):
        ids = identifiers(
            "Tan, A. (2021). Title. Journal, 3(2), 1-9. https://doi.org/10.1234/ABC.5."
        )
        assert ids.dois == {"10.1234/abc.5"}
        assert ids.urls == set()  # a doi.org URL counts as the DOI, not as a separate URL

    def test_doi_with_brackets_is_kept_whole(self):
        assert identifiers("doi:10.1002/(SICI)1097-4571(199806)49:8").dois == {
            "10.1002/(sici)1097-4571(199806)49:8"
        }

    def test_url(self):
        ids = identifiers("Retrieved from https://www.moe.gov.my/policy/ai/.")
        assert ids.urls == {"https://www.moe.gov.my/policy/ai"}

    def test_isbn_checksums(self):
        assert isbn_valid("978-0-306-40615-7")
        assert isbn_valid("0-306-40615-2")
        assert isbn_valid("080442957X")
        assert not isbn_valid("978-0-306-40615-8")
        assert not isbn_valid("12345")

    def test_valid_and_invalid_isbn_are_separated(self):
        ids = identifiers("Book. ISBN 978-0-306-40615-7. Other ISBN: 978-0-306-40615-8")
        assert ids.isbns == {"9780306406157"}
        assert ids.invalid_isbns == {"9780306406158"}
        assert ids.any

    def test_isbn_inside_a_springer_doi_is_not_an_isbn(self):
        ids = identifiers("Chapter. https://doi.org/10.1007/978-3-319-24277-4_9")
        assert ids.dois and not ids.isbns and not ids.invalid_isbns

    def test_nothing(self):
        assert not identifiers("Tan, A. (2022). AI in classrooms. Journal of Things.").any


class TestFabricationGuard:
    """A source the model proposed is never presented as verified."""

    def test_model_source_without_identifier_is_flagged(self):
        check = check_source(
            "Tan, A. (2022). AI in Malaysian classrooms. Journal of Things.", "model"
        )
        assert check.status == "flagged"
        assert "no_identifier" in check.flag_codes

    def test_model_source_with_only_an_invalid_isbn_is_flagged(self):
        check = check_source("A book. ISBN 978-0-306-40615-8", "model")
        assert check.status == "flagged"
        assert {"invalid_isbn", "no_identifier"} <= set(check.flag_codes)

    @pytest.mark.parametrize(
        "ref",
        [
            "Selwyn, N. (2019). Should robots replace teachers? Polity. ISBN 978-0-306-40615-7",
            "Tan, A. (2021). Title. Journal. https://doi.org/10.1234/abc",
            "MOE. (2023). Policy. https://www.moe.gov.my/x",
        ],
    )
    def test_model_source_with_identifier_is_still_only_unverified(self, ref):
        assert check_source(ref, "model").status == "unverified"

    def test_user_source_is_supplied_never_flagged(self):
        check = check_source("Tan, A. (2022). AI in classrooms. Journal of Things.", "user")
        assert check.status == "supplied"
        assert check.flag_codes == ["no_identifier"]  # a note, not an accusation

    def test_no_status_claims_verification(self):
        statuses = {
            check_source(r, o).status
            for r in ("x", "y https://doi.org/10.1/x")
            for o in ("user", "model")
        }
        assert statuses <= {"supplied", "unverified", "flagged"}


class TestCheckFormatted:
    def test_identifier_added_by_the_model_makes_entry_unverified(self):
        check = check_formatted(
            "Tan A 2021 Title Journal",
            "Tan, A. (2021). Title. Journal. https://doi.org/10.9999/made.up",
        )
        assert check.status == "unverified"
        assert ("identifier_added_by_ai", ["10.9999/made.up"]) in check.flags

    def test_doi_rewritten_as_url_is_not_an_addition(self):
        check = check_formatted(
            "Tan A 2021 Title Journal doi:10.1234/abc",
            "Tan, A. (2021). Title. Journal. https://doi.org/10.1234/abc",
        )
        assert check.status == "supplied"
        assert check.flags == []

    def test_dropped_identifier_is_noted(self):
        check = check_formatted("Book 2020 ISBN 978-0-306-40615-7", "Author. (2020). Book.")
        assert ("identifier_dropped", ["9780306406157"]) in check.flags


class TestSplitReferences:
    def test_one_per_line_with_numbering(self):
        assert split_references("[1] A. One.\n2. B. Two.\n- C. Three.\n") == [
            "A. One.",
            "B. Two.",
            "C. Three.",
        ]

    def test_blank_line_blocks_join_wrapped_lines(self):
        text = "Tan, A. (2021).\n  Title.\n\nLee, B. (2020). Other.\n"
        assert split_references(text) == ["Tan, A. (2021). Title.", "Lee, B. (2020). Other."]

    def test_heading_and_empty(self):
        assert split_references("References\nTan (2020) X") == ["Tan (2020) X"]
        assert split_references("  \n") == []


DRAFT_APA = """AI is changing teaching (Tan, 2021; Lee & Wong, 2020). Ahmad (2019) disagrees.

Some claims (World Health Organization, 2020) need care. Others cite (Missing, 2018).

## References

Ahmad, S. (2019). Title. Publisher.

Lee, B., & Wong, C. (2020). Title. https://doi.org/10.1/x

Tan, A. (2021). Title. Journal.

World Health Organization. (2020). Report.

Unused, Z. (2017). Never cited.
"""


class TestAnalyseDraft:
    def test_author_year_cross_check(self):
        r = analyse_draft(DRAFT_APA)
        assert r.has_reference_list
        assert {
            "Tan, 2021",
            "Lee, 2020",
            "Ahmad, 2019",
            "Organization, 2020",
            "Missing, 2018",
        } <= set(r.in_text)
        assert r.cited_not_listed == ["Missing, 2018"]
        assert r.listed_not_cited == ["Unused, Z. (2017). Never cited."]
        assert all(ref.status == "supplied" for ref in r.references)
        assert len(r.references) == 5

    def test_numeric_cross_check(self):
        text = (
            "Claim [1], [2-3] and [5]. Year [2020] is not a source.\n\n"
            "References\n\n[1] A\n\n[2] B\n\n[3] C\n\n[4] D\n"
        )
        r = analyse_draft(text)
        assert r.in_text == ["[1]", "[2]", "[3]", "[5]"]
        assert r.cited_not_listed == ["[5]"]
        assert r.listed_not_cited == ["D"]

    def test_malay_heading_and_dan(self):
        text = (
            "Kajian (Ahmad dan Ismail, 2020) menunjukkan.\n\n"
            "Rujukan\n\nAhmad, S., & Ismail, R. (2020). Tajuk.\n"
        )
        r = analyse_draft(text)
        assert r.in_text == ["Ahmad, 2020"]
        assert r.cited_not_listed == [] and r.listed_not_cited == []

    def test_no_reference_list(self):
        r = analyse_draft("A claim (Tan, 2021).")
        assert not r.has_reference_list
        assert r.in_text == ["Tan, 2021"]
        assert r.cited_not_listed == []
