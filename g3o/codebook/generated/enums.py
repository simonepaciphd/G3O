# GENERATED FILE - do not edit. Built from codebook/codebook.yaml by
# g3o.codebook.generators.enums.
# codebook release: 2.7 | codebook sha256: f0b1348cddbbe1ab0de8e16b80dae64a3e3400fe71788a6673f5cfc52348c72f
# Intended target: T-012 enum constants (g3o/common/contract.py or a module T-012 names).
"""Codebook value lists as constants; each carries its item id and item hash."""

from __future__ import annotations

CODEBOOK_RELEASE = '2.7'
CODEBOOK_SHA256 = 'f0b1348cddbbe1ab0de8e16b80dae64a3e3400fe71788a6673f5cfc52348c72f'

#: item id -> (item hash, value codes in codebook order)
ITEM_ENUMS: dict[str, tuple[str, tuple[str, ...]]] = {
    'core.page_verdict': ('d448710c4b15adc59edf76e6097a881a9bc0ab36221e9b895a8171c4f49abb0b', ('confirms_activity', 'ambiguous_genai', 'ambiguous_attribution', 'other_body', 'event_only', 'background_only', 'confirms_absence', 'no_genai', 'not_assessable',)),
    'core.disclosure_form': ('af8cdf4d03cce301d4733c5d1f4c29c8abfe0354366592f2237e91eba6b7b694', ('register_cross_institution', 'register_single_institution', 'mandated_report', 'formal_record', 'informal_official', 'third_party',)),
    'core.disclosure_scope': ('32e224fd58a2738763c9e708b84e4e8d0d24fc6c07c042d1aadc0d616be64617', ('whole_of_government', 'multi_institution', 'single_institution',)),
    'core.page_complete': ('a9f0477de324e7012112096cb6f65a79d6c95f891595b196f87fc11abb65e7fb', ('yes', 'no',)),
    'core.source_type': ('18fd64c5194e4ed8d3ac57036a9a29e58293264137772357e41d636a4747170f', ('news_major', 'news_trade', 'vendor', 'academic', 'policy_org', 'social_media', 'procurement_tender', 'other',)),
    'core.content_contact_named': ('c14b41bf44f0d1a22b5392ae792c7ffe24c51fb4c6e332bae0cf67064590febe', ('yes', 'no',)),
    'core.content_contact_details': ('6ef720c9b22a50994be0bde73ee626c26f1ac59fcf3808a3d72a2249c82b8bf7', ('yes', 'no',)),
    'core.content_data': ('32b7a48c23a51ba63beb865cae0f6b9c864a519c4d6a1af1ad825fdbd55e4592', ('yes', 'no',)),
    'core.activity_segment': ('44cc63f10ebef97a1402d517332330fb5ff41ffcf9de22de80b87a4f8e57b97e', ('same_activity', 'component_of_program', 'has_component', 'shared_participation', 'governs', 'governed_by', 'distinct_action', 'unresolved', 'not_an_activity',)),
    'core.observed_actor_relationship': ('16ddef0cb7e4102dbb09949a7f1ecdb7e9a5b19d4f99bf54148b4a1bc1b00b74', ('this_institution', 'unit_of_institution', 'joint_participant', 'other', 'unresolved',)),
    'core.activity_type': ('171e96a029766889465f3d0596bef25be502406a23e64cf85c060932d9e07b50', ('policy_guidance', 'pilot_experiment', 'program_initiative', 'internal_operational', 'public_facing_service',)),
    'core.action_type': ('5aaa9dc3449dfa95f1700b2d4aeccc1d7cbcf04b46af301121dd6192407e614b', ('deployment', 'governance', 'staff_training', 'program',)),
    'core.adoption_stage': ('199ba1e14fe71ca352701ab823081796103006e3d4ac2057bb093681ad1a59ff', ('proposed', 'announced', 'pilot', 'production', 'discontinued',)),
    'core.procurement_status': ('bba50c17230cfc52b5c8b90a5a1ed8782e446f8f0a333491722dd92ffd5eea25', ('none_documented', 'tender_or_rfp', 'award_or_contract', 'payment_or_subscription',)),
    'core.model_origin': ('ea3d7b2cadbf2f64522113b0d5e2dfa58915e56f0d473d998329056e016b210e', ('commercial', 'open_weight', 'government_developed',)),
    'core.build_arrangement': ('03c8be5d39bfee5cb16a6945bf343fa6b1764a15227183c8db87264ec7f3ab1c', ('off_the_shelf_product', 'custom_application_on_external_model', 'model_trained_or_fine_tuned_by_institution',)),
    'core.interface': ('75312626806d0d38c61dd1ce2f7301545b48ba622fe3f40d32e918e85774dc8b', ('conversational', 'backend_or_api', 'other_interface',)),
    'core.function_drafting_writing': ('563531506d7276798c955dcb142561d91d8fb0f760d16474334df91e75d52cf4', ('yes', 'no',)),
    'core.function_summarization': ('d698879c119d6831964e88cafef1d8b813ea3e3c9734410f25c21c09e0615a93', ('yes', 'no',)),
    'core.function_translation': ('2466a158bf8871215a3dcc9540f4ddda1676d4ff15e4bfec70820c5fd3cd2836', ('yes', 'no',)),
    'core.function_search_retrieval': ('7f779b3d306cd266e9a2d3732767f3b2b9a101f3e5e4218683a1de77690e3364', ('yes', 'no',)),
    'core.function_code': ('f5d7bbaf1b034e3b147d3e1d8db7071f50f6ab0d2e8e35ed7dfe44f2abb7823f', ('yes', 'no',)),
    'core.function_image_audio_video': ('1e5956075de2cc48026418d5d81f52981f893c0ecfdb928a7b55876115f96f03', ('yes', 'no',)),
    'core.function_extraction_classification': ('155f87129441c51e70c713d3d85bb10369421c66ec949443e57fdbefc1043291', ('yes', 'no',)),
    'core.function_analysis_recommendation': ('a8026858596464541592c242ad14e9f56a02538a93fb29b1587cef9980f60509', ('yes', 'no',)),
    'core.deployment_mode': ('d8e2608aeb147a2f4a0158523be100174bce0af2cb2d2ae909eaf7f8ceda3104', ('integrated', 'standalone',)),
    'core.target_users': ('7a11470600f2085adb6fa27b888a52d431b5f187bf2ebb9e6b9edcdb248902b7', ('internal_staff', 'public', 'both',)),
    'core.governed_population': ('b7e4f250f93adbdc0a3d7c9c1ff4a93aed888e5d8555ecb800bdcc946c9136c5', ('internal_personnel', 'external_users', 'both',)),
    'core.governance_form': ('5a68086467795ad4b1d057e7330020e2397a4f42ed2eaf6f611bbc1b34308fa5', ('dedicated_genai_or_ai_policy_or_guideline', 'approved_tool_list_or_endorsement', 'clause_in_instrument_on_other_subject', 'court_or_regulatory_order', 'procurement_standard',)),
    'core.governance_direction': ('c0c9559b087615ee1a68b39decf9623b138e4b12ff2cf0eaeeaf8cdc04cccced', ('prohibits', 'restricts_with_conditions', 'permits', 'requires', 'promotes',)),
    'core.service_domain': ('b3b632c1f7f3cab32d8847cc59a65316ebc0992d6e076bb1ec6d02478870bb54', ('general_public_services', 'defence', 'public_order_safety', 'economic_affairs', 'environmental_protection', 'housing_community_amenities', 'health', 'recreation_culture_religion', 'education', 'social_protection', 'other',)),
    'core.genai_mechanism_basis': ('aef25db05adf60be6f2aa9ecd0c28636e6cac17dfcbb221bbdfbe5443b643cc0', ('named_genai_product_or_model', 'explicit_genai_label', 'generative_capability_described', 'ai_chatbot_or_assistant_label_only',)),
    'core.deployment_scale_unit': ('4a7cc03581fd7c61950d556903bdccfcf4bcdd5485ab782d5412cb0992d63a71', ('licences_or_seats', 'users', 'interactions', 'units_or_departments', 'none',)),
    'core.has_human_oversight': ('d4a11f0e37de294a9d09c27581a803ad795e03d71e863ab31418040e55660046', ('yes', 'no', 'unclear',)),
    'core.has_transparency_notice': ('63177f84cc942627dda8273ba841c33e3fa75b963691c4fffb3bcec40566ef0d', ('yes', 'no', 'unclear',)),
    'core.has_data_classification': ('c0a9a902c3e1dac3fda8ef2ec62bed86ed0e67276965684e8328b8ba0e100ed2', ('yes', 'no', 'unclear',)),
    'core.has_risk_assessment': ('56e835cc7f5744706d0502ca37f5d296458c7ab7d5d12aa5372066d1107563cb', ('yes', 'no', 'unclear',)),
    'core.outcome_kind': ('80a037b895fd0d167505a50b6760a28199c8e5a3d2734f5183f356742d9b50c8', ('quantified', 'qualitative', 'none_reported',)),
    'core.incident_kind': ('8d59c74ce433b2e99bab93f90d38b6949d27c74bec470c39f2c41fac49301ee5', ('quantified', 'qualitative', 'none_reported', 'discontinuation_uncertain',)),
    'core.evaluation_documented': ('c769fcddf1fa71e4e91e4947ce96716448de13f9881a9eab6fbb931169482e24', ('results_reported', 'conducted_no_results', 'required_or_planned', 'unclear',)),
    'core.evaluation_type_pre_deployment_testing': ('805b0cbbb2fe62c8a62f35192934ed7a20dfc12e0c2c4479b85366251bda34f4', ('yes', 'no',)),
    'core.evaluation_type_pilot_evaluation': ('bc48c7ebb08729c2671fa4e16cf87be1ed0c35226893c896dbf1ee2eee7991f3', ('yes', 'no',)),
    'core.evaluation_type_independent_audit': ('efea36e1378b9a138191c882aaa10a431902b39926cea2714d9dfbd1465f2d84', ('yes', 'no',)),
    'core.evaluation_type_ongoing_monitoring': ('92d011d484c3821e59f55f6c7c6b6153250b7c453d84c1d0055125c409255817', ('yes', 'no',)),
    'core.evaluation_type_user_feedback': ('8c01f238f78f94fddf6fd0a5289181cd9653a6c0ffd33f278c4a339929b7d0cd', ('yes', 'no',)),
    'core.evaluation_type_bias_or_safety_testing': ('8c9b4323a9cfa5d921a11c442f87566af8df9f7ace0279ad675ece3469401d56', ('yes', 'no',)),
    'core.support_entailment': ('f9f841754b15eac328de8a33ff5c089c96dec33b4e4ac774665c5fa399e4e3cc', ('true', 'false',)),
    'core.activity_relation_cross_page': ('fea0b4ce0e16c47f1177145937bc9d96f11f84f156899c9dd171f21782dd919c', ('same_activity', 'component_of_program', 'has_component', 'shared_participation', 'governs', 'governed_by', 'distinct_action', 'unresolved',)),
    'core.observed_actor_role': ('3b56edcce15ceda21e23aeebfcfc26112da874809ac7002e3562d8808e8f5aa4', ('institutional_actor', 'issuer', 'participant', 'external_speaker', 'service_provider', 'event_host',)),
    'core.support_status_second_reason': ('15278c373296fcd2164444cc29b816e0d773a02d940a21b28f78a49c701fc90d', ('downgraded_no_quote', 'downgraded_low_confidence', 'downgraded_quote_not_stating_value',)),
}

#: (item id, part) -> value codes, for items in the parts form (first part as ITEM_ENUMS)
ITEM_PART_ENUMS: dict[tuple[str, str], tuple[str, ...]] = {
    ('core.observed_actor_relationship', 'relationship'): ('this_institution', 'unit_of_institution', 'joint_participant', 'other', 'unresolved',),
    ('core.observed_actor_relationship', 'searched_institution_role'): ('contracting_authority', 'beneficiary', 'central_purchasing_body', 'unit', 'joint',),
}

PAGE_VERDICT = ITEM_ENUMS['core.page_verdict'][1]  # core.page_verdict
DISCLOSURE_FORM = ITEM_ENUMS['core.disclosure_form'][1]  # core.disclosure_form
DISCLOSURE_SCOPE = ITEM_ENUMS['core.disclosure_scope'][1]  # core.disclosure_scope
PAGE_COMPLETE = ITEM_ENUMS['core.page_complete'][1]  # core.page_complete
SOURCE_TYPE = ITEM_ENUMS['core.source_type'][1]  # core.source_type
CONTENT_CONTACT_NAMED = ITEM_ENUMS['core.content_contact_named'][1]  # core.content_contact_named
CONTENT_CONTACT_DETAILS = ITEM_ENUMS['core.content_contact_details'][1]  # core.content_contact_details
CONTENT_DATA = ITEM_ENUMS['core.content_data'][1]  # core.content_data
ACTIVITY_RELATION_WITHIN_PAGE = ITEM_ENUMS['core.activity_segment'][1]  # core.activity_segment
OBSERVED_ACTOR_RELATIONSHIP = ITEM_ENUMS['core.observed_actor_relationship'][1]  # core.observed_actor_relationship
ACTIVITY_TYPE = ITEM_ENUMS['core.activity_type'][1]  # core.activity_type
ACTION_TYPE = ITEM_ENUMS['core.action_type'][1]  # core.action_type
ADOPTION_STAGE = ITEM_ENUMS['core.adoption_stage'][1]  # core.adoption_stage
PROCUREMENT_STATUS = ITEM_ENUMS['core.procurement_status'][1]  # core.procurement_status
MODEL_ORIGIN = ITEM_ENUMS['core.model_origin'][1]  # core.model_origin
BUILD_ARRANGEMENT = ITEM_ENUMS['core.build_arrangement'][1]  # core.build_arrangement
INTERFACE = ITEM_ENUMS['core.interface'][1]  # core.interface
FUNCTION_DRAFTING_WRITING = ITEM_ENUMS['core.function_drafting_writing'][1]  # core.function_drafting_writing
FUNCTION_SUMMARIZATION = ITEM_ENUMS['core.function_summarization'][1]  # core.function_summarization
FUNCTION_TRANSLATION = ITEM_ENUMS['core.function_translation'][1]  # core.function_translation
FUNCTION_SEARCH_RETRIEVAL = ITEM_ENUMS['core.function_search_retrieval'][1]  # core.function_search_retrieval
FUNCTION_CODE = ITEM_ENUMS['core.function_code'][1]  # core.function_code
FUNCTION_IMAGE_AUDIO_VIDEO = ITEM_ENUMS['core.function_image_audio_video'][1]  # core.function_image_audio_video
FUNCTION_EXTRACTION_CLASSIFICATION = ITEM_ENUMS['core.function_extraction_classification'][1]  # core.function_extraction_classification
FUNCTION_ANALYSIS_RECOMMENDATION = ITEM_ENUMS['core.function_analysis_recommendation'][1]  # core.function_analysis_recommendation
DEPLOYMENT_MODE = ITEM_ENUMS['core.deployment_mode'][1]  # core.deployment_mode
TARGET_USERS = ITEM_ENUMS['core.target_users'][1]  # core.target_users
GOVERNED_POPULATION = ITEM_ENUMS['core.governed_population'][1]  # core.governed_population
GOVERNANCE_FORM = ITEM_ENUMS['core.governance_form'][1]  # core.governance_form
GOVERNANCE_DIRECTION = ITEM_ENUMS['core.governance_direction'][1]  # core.governance_direction
SERVICE_DOMAIN = ITEM_ENUMS['core.service_domain'][1]  # core.service_domain
GENAI_MECHANISM_BASIS = ITEM_ENUMS['core.genai_mechanism_basis'][1]  # core.genai_mechanism_basis
DEPLOYMENT_SCALE_UNIT = ITEM_ENUMS['core.deployment_scale_unit'][1]  # core.deployment_scale_unit
HAS_HUMAN_OVERSIGHT = ITEM_ENUMS['core.has_human_oversight'][1]  # core.has_human_oversight
HAS_TRANSPARENCY_NOTICE = ITEM_ENUMS['core.has_transparency_notice'][1]  # core.has_transparency_notice
HAS_DATA_CLASSIFICATION = ITEM_ENUMS['core.has_data_classification'][1]  # core.has_data_classification
HAS_RISK_ASSESSMENT = ITEM_ENUMS['core.has_risk_assessment'][1]  # core.has_risk_assessment
OUTCOME_KIND = ITEM_ENUMS['core.outcome_kind'][1]  # core.outcome_kind
INCIDENT_KIND = ITEM_ENUMS['core.incident_kind'][1]  # core.incident_kind
EVALUATION_DOCUMENTED = ITEM_ENUMS['core.evaluation_documented'][1]  # core.evaluation_documented
EVALUATION_TYPE_PRE_DEPLOYMENT_TESTING = ITEM_ENUMS['core.evaluation_type_pre_deployment_testing'][1]  # core.evaluation_type_pre_deployment_testing
EVALUATION_TYPE_PILOT_EVALUATION = ITEM_ENUMS['core.evaluation_type_pilot_evaluation'][1]  # core.evaluation_type_pilot_evaluation
EVALUATION_TYPE_INDEPENDENT_AUDIT = ITEM_ENUMS['core.evaluation_type_independent_audit'][1]  # core.evaluation_type_independent_audit
EVALUATION_TYPE_ONGOING_MONITORING = ITEM_ENUMS['core.evaluation_type_ongoing_monitoring'][1]  # core.evaluation_type_ongoing_monitoring
EVALUATION_TYPE_USER_FEEDBACK = ITEM_ENUMS['core.evaluation_type_user_feedback'][1]  # core.evaluation_type_user_feedback
EVALUATION_TYPE_BIAS_OR_SAFETY_TESTING = ITEM_ENUMS['core.evaluation_type_bias_or_safety_testing'][1]  # core.evaluation_type_bias_or_safety_testing
SUPPORT_ENTAILMENT = ITEM_ENUMS['core.support_entailment'][1]  # core.support_entailment
ACTIVITY_RELATION = ITEM_ENUMS['core.activity_relation_cross_page'][1]  # core.activity_relation_cross_page
OBSERVED_ACTOR_ROLE = ITEM_ENUMS['core.observed_actor_role'][1]  # core.observed_actor_role
SUPPORT_STATUS_SECOND_REASON = ITEM_ENUMS['core.support_status_second_reason'][1]  # core.support_status_second_reason
