# GENERATED FILE - do not edit. Built from codebook/codebook.yaml by
# g3o.codebook.generators.enums.
# codebook release: 2.7 | codebook sha256: d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764
# Intended target: T-012 enum constants (g3o/common/contract.py or a module T-012 names).
"""Codebook value lists as constants; each carries its item id and item hash."""

from __future__ import annotations

CODEBOOK_RELEASE = '2.7'
CODEBOOK_SHA256 = 'd24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764'

#: item id -> (item hash, value codes in codebook order)
ITEM_ENUMS: dict[str, tuple[str, tuple[str, ...]]] = {
    'core.page_verdict': ('fd63c805b56f323f6b330288afd8d12429e0b7e2e53b5397a2feae37a2e22f75', ('confirms_activity', 'ambiguous_genai', 'ambiguous_attribution', 'other_body', 'event_only', 'background_only', 'confirms_absence', 'no_genai', 'not_assessable',)),
    'core.disclosure_form': ('09cf9815915325c5bd2f8360c7df2821d73c779f829111a5683ebd2b56dcaac9', ('register_cross_institution', 'register_single_institution', 'mandated_report', 'formal_record', 'informal_official', 'third_party',)),
    'core.disclosure_scope': ('628eef37275d69d7e443f582adda3242f857898a17311c7d0240482730f58868', ('whole_of_government', 'multi_institution', 'single_institution',)),
    'core.page_complete': ('aa535149e9d7875984e77693fae7af0fd1f205ad48852a9fe3bd856f1f184d14', ('yes', 'no',)),
    'core.source_type': ('0008679290c739d3727328af7302d232ef1024cbf908136157fefe819194a76e', ('news_major', 'news_trade', 'vendor', 'academic', 'policy_org', 'social_media', 'procurement_tender', 'other',)),
    'core.content_contact_named': ('715fb22182701f236290cb74b351e21b7f78deadf88ad177f90b65b05b413995', ('yes', 'no',)),
    'core.content_contact_details': ('c6e78dae75bb317ad353f8d38c074a99309570906f0fbccb1e4e29913d1e88ac', ('yes', 'no',)),
    'core.content_data': ('d4c082c3cd02bb721a676870aa414ecb99862a25ba4a616d913a1dff2c9a6014', ('yes', 'no',)),
    'core.activity_segment': ('682fa27ba8f84d627704cf7f1cfdae2dec8dcf1361701f04355bd3c12d3e24a6', ('same_activity', 'component_of_program', 'has_component', 'shared_participation', 'governs', 'governed_by', 'distinct_action', 'unresolved', 'not_an_activity',)),
    'core.activity_type': ('747a666fe663dd4371968d1bb061c0bd5a9d5879b131474fb53b002900c121f9', ('policy_guidance', 'pilot_experiment', 'program_initiative', 'internal_operational', 'public_facing_service',)),
    'core.action_type': ('85ed03a3421b4a8e7d3dcfaf411bf365a543d05cff8b00bfcabf5cca27ff0131', ('deployment', 'governance', 'staff_training', 'program',)),
    'core.adoption_stage': ('c2792d68cd20786326873e3bd3c3d30ae47e431fb8f7e79cd85a3998fae815bc', ('proposed', 'announced', 'pilot', 'production', 'discontinued',)),
    'core.procurement_status': ('58c5ee8463a406a72a6126a76b2328fe9b7f760b2d06d510ea5399070137c067', ('none_documented', 'tender_or_rfp', 'award_or_contract', 'payment_or_subscription',)),
    'core.model_origin': ('e707525beafe92682470f295f6a3698a11b4ea62a4a037b51a811d7d0229717c', ('commercial', 'open_weight', 'government_developed',)),
    'core.build_arrangement': ('cb8c1de57bfc0cbbc2a04462a910f62ecf0e7244539f449eb02e52767e847367', ('off_the_shelf_product', 'custom_application_on_external_model', 'model_trained_or_fine_tuned_by_institution',)),
    'core.interface': ('c3ee2916f682225c020da3c984b0b43de29fba82c89192e0121d0777cc12a609', ('conversational', 'backend_or_api', 'other_interface',)),
    'core.function_drafting_writing': ('c21dd32f1b659edf30de9eb1f67d4f9f28b284186936fadb8cbad6beedfaa36a', ('yes', 'no',)),
    'core.function_summarization': ('a9556d12c63b142b658400e09842645429bcd7ae1212b3ad57e1e9b5efe4722a', ('yes', 'no',)),
    'core.function_translation': ('149059df8c5d72b42c0ca1dcee4e85eed3336600b5a7eba9e44e95055d2a4e33', ('yes', 'no',)),
    'core.function_search_retrieval': ('e5099ebac371dbafd5bc1ced2a18a0c2f1fd1c394c85dc9646bbb35c832b9101', ('yes', 'no',)),
    'core.function_code': ('9a8ffa6538b549724c8cfb2c5688c4ee7e72dd3840a2e0c682d6ee28467f61ab', ('yes', 'no',)),
    'core.function_image_audio_video': ('bf683421e2544ede91205041d9dfec1419c5cd55180bebeed64e0ed7bd5bb3a7', ('yes', 'no',)),
    'core.function_extraction_classification': ('f2127d70ceed5bb5bed14a924d08591cee5d29841cdf072a02583dd8e45e550b', ('yes', 'no',)),
    'core.function_analysis_recommendation': ('6f6c4ee0ad101664c8ffb39f0a182a76baf21b1e7a9af80044f9d48a5d831560', ('yes', 'no',)),
    'core.deployment_mode': ('e9160a52e14cdec94954a5ebc06659530de0027b705d6a7cf86b351cb7e0c90b', ('integrated', 'standalone',)),
    'core.target_users': ('81b0492719d9b307f44ef4ee5b2bec3edfae804d90980ab9b076aba2178a928d', ('internal_staff', 'public', 'both',)),
    'core.governed_population': ('8548e8dbd51ea4a8c03dc0aa0b53b7a2e70cf495c3ed7eeeb2da82faee7c582b', ('internal_personnel', 'external_users', 'both',)),
    'core.governance_form': ('1022dfd04964d1ddc24f2604645f6c15f13b769e42a00f3686e5ba8cfea26fea', ('dedicated_genai_or_ai_policy_or_guideline', 'approved_tool_list_or_endorsement', 'clause_in_instrument_on_other_subject', 'court_or_regulatory_order', 'procurement_standard',)),
    'core.governance_direction': ('3c1d1277c4675ae3f17ef40058f9a08e9daffb352d75934037723bc1e5cbf5c3', ('prohibits', 'restricts_with_conditions', 'permits', 'requires', 'promotes',)),
    'core.service_domain': ('cd57c8b15002f6d8218e8d4f6e3012a147415c0799f8a664f3488bd38bbcadf5', ('general_public_services', 'defence', 'public_order_safety', 'economic_affairs', 'environmental_protection', 'housing_community_amenities', 'health', 'recreation_culture_religion', 'education', 'social_protection', 'other',)),
    'core.genai_mechanism_basis': ('8386c42537ca24971610796d9c7fca06aacd3e0988b13ce4109e79131b3ebb1e', ('named_genai_product_or_model', 'explicit_genai_label', 'generative_capability_described', 'ai_chatbot_or_assistant_label_only',)),
    'core.deployment_scale_unit': ('da0f1f763a76751f02792b920c7cbbb52a0bf11950f4f96c6780d736b4eed8d6', ('licences_or_seats', 'users', 'interactions', 'units_or_departments', 'none',)),
    'core.has_human_oversight': ('3c2001c829bacae4f2f7e3961d8e95c0b7345000c1903cd508cc411d63ce4769', ('yes', 'no', 'unclear',)),
    'core.has_transparency_notice': ('992b6e22dcd511270d2adf2d2fe96ff95bd8cb5b2d1e2bd6e89fc47fac8447c7', ('yes', 'no', 'unclear',)),
    'core.has_data_classification': ('68084992dbde87ad50504404f47dc4e6ec31d81952f10f34b3dd443ebcc8495c', ('yes', 'no', 'unclear',)),
    'core.has_risk_assessment': ('2698cd63443ceb8088c716d3b611c26273c2a560366fc7cef8dfba1f05dbdfbf', ('yes', 'no', 'unclear',)),
    'core.outcome_kind': ('75a57dacf1821fb733a64d2bbd44f2aa043845b38c9054065820009069dc1577', ('quantified', 'qualitative', 'none_reported',)),
    'core.incident_kind': ('1783196e41d3163a3b7348d956bcc4ef0af9b79c400a0484d44bd11d71ced9cc', ('quantified', 'qualitative', 'none_reported', 'discontinuation_uncertain',)),
    'core.evaluation_documented': ('eb98377467f2a74928e96fe901cb43eae39c10be2d8bf1297696cb1f020f222a', ('results_reported', 'conducted_no_results', 'required_or_planned', 'unclear',)),
    'core.evaluation_type_pre_deployment_testing': ('ea5987af915a041e5c2629de6903c29c2470f6b023517c483bda41d5ebaa612c', ('yes', 'no',)),
    'core.evaluation_type_pilot_evaluation': ('27e0db2eb31011d4c8d4361ddd4861dc01926b00059885c572a6ff6ea8170753', ('yes', 'no',)),
    'core.evaluation_type_independent_audit': ('4ebf5ba2d6a3e533b6730c91c06a04879929634af735a8971a73f40f5d2cd45a', ('yes', 'no',)),
    'core.evaluation_type_ongoing_monitoring': ('3a1627cf8f0e2e710baed963c501b85f52f0224699f755eec778eac398376c7e', ('yes', 'no',)),
    'core.evaluation_type_user_feedback': ('1e0155dd412152c3f036b7d27569ebc10b6375a64eda51b1b6942c77dec246b9', ('yes', 'no',)),
    'core.evaluation_type_bias_or_safety_testing': ('8486f5e9bc9211779b9ae13597c14dbe9b2d5680ec830fafee2a7c485e538843', ('yes', 'no',)),
    'core.support_entailment': ('57ebd9eca0dfe0732fb9deb3aa4bc740a21deaf1282aca3ce92a17c2d066b839', ('true', 'false',)),
    'core.activity_relation_cross_page': ('ed35aa6219ba9851bd5efe12e220a94855a87f1e601e726119547a30b02857c3', ('same_activity', 'component_of_program', 'has_component', 'shared_participation', 'governs', 'governed_by', 'distinct_action', 'unresolved',)),
    'core.observed_actor_role': ('e045ce6235185b64555efa5530f3de196f55ba70e6149f5d529720029abf5367', ('institutional_actor', 'issuer', 'participant', 'external_speaker', 'service_provider', 'event_host',)),
    'core.support_status_second_reason': ('e782c3663184e51a96ff21bcf305c9fa647a453faa15ca95529c1f66072fa65a', ('downgraded_no_quote', 'downgraded_low_confidence', 'downgraded_quote_not_stating_value',)),
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
