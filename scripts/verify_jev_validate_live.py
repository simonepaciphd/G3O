#!/usr/bin/env python3
"""Live API verification for jev_validate module."""


from dotenv import load_dotenv

from g3o.common.credentials import Credentials, resolve
from g3o.common.jev_client import ask, client_from_credentials
from g3o.validate.jev_validate import (
    build_validate_questions,
    build_validate_state,
    parse_validate_result,
)

load_dotenv()


def verify_jev_validate():
    """Verify jev_validate module with live API call."""
    print("=" * 60)
    print("JEV VALIDATE LIVE API VERIFICATION")
    print("=" * 60)

    # Resolve credentials
    credentials = resolve(Credentials())
    if not credentials.typesafe_api_key:
        print("ERROR: TYPESAFE_API_KEY not found in environment")
        return False

    print(f"\n✓ TypeSafe API key resolved (fingerprint: {credentials.typesafe_fingerprint})")

    # Create client
    client = client_from_credentials(credentials)
    print("✓ Jev client created")

    # Sample institution data
    institution_row = {
        "institution_id": "INST-TEST-001",
        "institution_name": "Test Government Agency",
        "country": "US",
        "branch_of_government": "executive",
        "level_of_government": "national",
        "institution_search_languages": "en",
    }

    # Sample input rows (simulating Stage 5 extract output)
    input_rows = [
        {
            "activity_name": "AI Chatbot for Citizen Services",
            "genai_evidence": "confirms_activity",
            "source_url": "https://example.gov/ai-initiative",
            "source_title": "AI Initiative Announcement",
            "source_publication_date": "2024-01-15",
            "source_access_date": "2024-06-01",
            "source_type": "official_gov",
            "source_language": "en",
            "source_credibility": "high",
            "source_snippet": "We launched an AI chatbot to help citizens access government services.",
            "confidence": "high",
            "uncertainty_flags": "none",
            "institution_summary": "Agency launched AI chatbot for citizen services.",
            "activity_type": "public_facing_service",
            "adoption_stage": "production",
            "access_type": "proprietary_vendor",
            "interaction_type": "chatbot",
            "tool_name": "ChatGPT",
            "vendor": "OpenAI",
            "deployment_mode": "standalone",
            "target_users": "public",
            "year_announced": "2024",
            "year_deployed": "2024",
            "has_human_oversight": "yes",
            "has_transparency_notice": "yes",
            "has_data_classification": "yes",
            "has_risk_assessment": "yes",
            "reported_outcomes": "none_reported",
            "reported_incidents": "none_reported",
            "scope_notes": "none",
        },
        {
            "activity_name": "AI Chatbot for Citizen Services",
            "genai_evidence": "confirms_activity",
            "source_url": "https://news.example.gov/ai-chatbot",
            "source_title": "News Article About AI Chatbot",
            "source_publication_date": "2024-02-01",
            "source_access_date": "2024-06-01",
            "source_type": "news_major",
            "source_language": "en",
            "source_credibility": "medium",
            "source_snippet": "The agency's new AI chatbot is now live.",
            "confidence": "medium",
            "uncertainty_flags": "none",
            "institution_summary": "AI chatbot launched in February 2024.",
            "activity_type": "public_facing_service",
            "adoption_stage": "production",
            "access_type": "proprietary_vendor",
            "interaction_type": "chatbot",
            "tool_name": "ChatGPT",
            "vendor": "OpenAI",
            "deployment_mode": "standalone",
            "target_users": "public",
            "year_announced": "2024",
            "year_deployed": "2024",
            "has_human_oversight": "yes",
            "has_transparency_notice": "yes",
            "has_data_classification": "yes",
            "has_risk_assessment": "yes",
            "reported_outcomes": "none_reported",
            "reported_incidents": "none_reported",
            "scope_notes": "none",
        },
    ]

    n_input_pages = 2

    print("\n✓ Test data prepared:")
    print(f"  - Institution: {institution_row['institution_name']}")
    print(f"  - Input rows: {len(input_rows)}")
    print(f"  - Input pages: {n_input_pages}")

    # Build state and questions
    print("\n→ Building jev state and questions...")
    state = build_validate_state(institution_row, input_rows, n_input_pages)
    questions = build_validate_questions(input_rows)

    print(f"✓ State built (keys: {list(state.keys())})")
    # Call jev API
    print("\n→ Calling jev API...")
    try:
        result = ask(
            state=state,
            questions=questions,
            client=client,
            model="jev-1.13.0",
        )
        print("✓ API call successful")
        print(f"  - Response model: {result.response_model}")
        print(f"  - Request ID: {result.request_id}")
        print(f"  - Usage: {result.input_tokens} input tokens, {result.output_tokens} output tokens")

        # Parse result
        print("\n→ Parsing jev result...")
        parsed = parse_validate_result(result, institution_row, input_rows, n_input_pages)
        print("✓ Result parsed successfully")
        print(f"  - Activity groups: {len(parsed.activity_groups)}")
        print(f"  - Conflict resolutions: {len(parsed.conflict_resolutions)}")
        print(f"  - Summary choice: {parsed.summary_choice}")

        # Validate response
        response = parsed.response
        print("\n✓ ConsolidatedInstitutionResponse validated:")
        print(f"  - Institution ID: {response.institution.institution_id}")
        print(f"  - Has GenAI activity: {response.institution.has_genai_activity}")
        print(f"  - Activities: {len(response.activities)}")
        print(f"  - Sources: {len(response.sources)}")

        if response.activities:
            print("\n  Activity details:")
            for i, activity in enumerate(response.activities, 1):
                print(f"    {i}. {activity.activity_name}")
                print(f"       - Type: {activity.activity_type}")
                print(f"       - Stage: {activity.adoption_stage}")
                print(f"       - Tool: {activity.tool_name}")
                print(f"       - Vendor: {activity.vendor}")
                print(f"       - N sources: {activity.n_sources}")
                print(f"       - Confidence: {activity.confidence}")

        print("\n" + "=" * 60)
        print("✓ LIVE API VERIFICATION SUCCESSFUL")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = verify_jev_validate()
    exit(0 if success else 1)
