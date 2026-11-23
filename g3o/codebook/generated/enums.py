# GENERATED FILE - do not edit. Built from codebook/codebook.yaml by
# g3o.codebook.generators.enums.
# codebook release: 2.7 | codebook sha256: dd3cc7e9c7e7dd9c9031f242001350ae730d418f9a8915affc2a08a85675c08b
# Intended target: T-012 enum constants (g3o/common/contract.py or a module T-012 names).
"""Codebook value lists as constants; each carries its item id and item hash."""

from __future__ import annotations

CODEBOOK_RELEASE = '2.7'
CODEBOOK_SHA256 = 'dd3cc7e9c7e7dd9c9031f242001350ae730d418f9a8915affc2a08a85675c08b'

#: item id -> (item hash, value codes in codebook order)
ITEM_ENUMS: dict[str, tuple[str, tuple[str, ...]]] = {
    'core.page_verdict': ('f3224d00890eba351b1b5b696c2d6eacdf7f3863c010e0a99de35216d1fa0bfe', ('confirms_activity', 'ambiguous_genai', 'ambiguous_attribution', 'other_body', 'event_only', 'background_only', 'confirms_absence', 'no_genai', 'not_assessable',)),
    'core.disclosure_form': ('4c7908f12b580b3e4e8a7be9d770ead29af77e02f08681fc291c854d70394907', ('register_cross_institution', 'register_single_institution', 'mandated_report', 'formal_record', 'informal_official', 'third_party',)),
    'core.disclosure_scope': ('bbf20d49f25291065f7e23d8da177e661d18017fb41dcfb7ec2ebcc07a75fe9c', ('whole_of_government', 'multi_institution', 'single_institution',)),
    'core.page_complete': ('113384334a8758749a57c8b6e25c7f77680c397198b7c4a26d4e40b997c91f5e', ('yes', 'no',)),
    'core.source_type': ('5d2e196e4b10755e018d1d822130b9ce51cd0f21f01b856aae21f6d90610ae3a', ('news_major', 'news_trade', 'vendor', 'academic', 'policy_org', 'social_media', 'procurement_tender', 'other',)),
    'core.content_contact_named': ('c14e3b5271cb6b4e8df73f4dcb77100ec06c3adc4c04a5ebe592f12bbdf28c8f', ('yes', 'no',)),
    'core.content_contact_details': ('d28c7a2aee5b9a1370e7049188e8f2f95512a04bb7d0abc40e442c2d0e5b7f53', ('yes', 'no',)),
    'core.content_data': ('7c5141d851e5c3912b9b926a4ab4e5d89d8f8df3e931531ef095f47cd28b3434', ('yes', 'no',)),
    'core.activity_segment': ('1b7750af042738acd295133cb4b1a14e0cfb189619952074db0f3607cfef5f17', ('same_activity', 'component_of_program', 'has_component', 'shared_participation', 'governs', 'governed_by', 'distinct_action', 'unresolved', 'not_an_activity',)),
    'core.observed_actor_relationship': ('39da975c8e44b9e211870b552eb4ab4ae2fc3669406842f39c7f0a6abc0a014d', ('this_institution', 'unit_of_institution', 'joint_participant', 'other', 'unresolved',)),
    'core.activity_type': ('82fed996275e4d042efea9bea6935308cd9e2c79469ed39135601b6a3af9a742', ('policy_guidance', 'pilot_experiment', 'program_initiative', 'internal_operational', 'public_facing_service',)),
    'core.action_type': ('cc49f966c1a02a32489091c718ee1fd94896f341158ca1a2788cd37253ef78d1', ('deployment', 'governance', 'staff_training', 'program',)),
    'core.adoption_stage': ('7bb0b0e80894be92f16d6bc51778b7de0dc0a09dd13355860518cb03632a0dd6', ('proposed', 'announced', 'pilot', 'production', 'discontinued',)),
    'core.procurement_status': ('6a27a7df087d81ee84d1a80ae4493c71aba22288d8e9852882b5e37682440820', ('none_documented', 'tender_or_rfp', 'award_or_contract', 'payment_or_subscription',)),
    'core.model_origin': ('a8eccc5010f668b465e986fc3fd060716ff41a7ee9dcd25eff4e70100d1262f6', ('commercial', 'open_weight', 'government_developed',)),
    'core.build_arrangement': ('5ad6eb5e066f8167db901e699752996fe8ace4c3bba4c615e77e766e3ebab582', ('off_the_shelf_product', 'custom_application_on_external_model', 'model_trained_or_fine_tuned_by_institution',)),
    'core.interface': ('7ff9950b948b59cf784f3303003661c59aa9d0fa285ac9829255eb909c84d8b2', ('conversational', 'backend_or_api', 'other_interface',)),
    'core.function_drafting_writing': ('9d4a44529aa69940a10a092f981ef8aabed9aeb7c82c2de0d32d22757676c481', ('yes', 'no',)),
    'core.function_summarization': ('134e27de8e50c257d2916e7e5f82c3e9333c1a5469ae6fd582a091fd48581373', ('yes', 'no',)),
    'core.function_translation': ('08bcc42a47982423b900361d535646758863d637d4c8f5b96280dfc232cc7603', ('yes', 'no',)),
    'core.function_search_retrieval': ('a9d975c026c25b4ab93cad2a6e6917a394bd2ea42a94bc4e8676c103255c4877', ('yes', 'no',)),
    'core.function_code': ('04ec6ce8f32cb2105118b4f45e56c88be084fb2918dddb5472b0fd20e4b1edfa', ('yes', 'no',)),
    'core.function_image_audio_video': ('31fcf07acca54ccbeca7637feb59496c407059a2e8eafc17e97b8a4f822dda81', ('yes', 'no',)),
    'core.function_extraction_classification': ('5b6fd7b8062937a905121023bbfe841b4a22936d1f3190e712a36cef331ddbfc', ('yes', 'no',)),
    'core.function_analysis_recommendation': ('4a973c2f1e681855c13ae910fc161c7c408dc362ab85015b8b3873c46ac44cb9', ('yes', 'no',)),
    'core.deployment_mode': ('ed5672b2fed226dd6a980bec93b1b15edb9d943ae4d08eeea596d69b8377008c', ('integrated', 'standalone',)),
    'core.target_users': ('fd900391b467a5aade9e8ddba9eb1c3da8247f681ccf54cbe1867015410b4a64', ('internal_staff', 'public', 'both',)),
    'core.governed_population': ('84b1eabcc7e258f67d556996506aa8436b3ed51e0b32865b2b9594f9182cc3e3', ('internal_personnel', 'external_users', 'both',)),
    'core.governance_form': ('9b84ef67dcb070a32922917d06ab5a956193261e27e713de958b3f34a14bf93a', ('dedicated_genai_or_ai_policy_or_guideline', 'approved_tool_list_or_endorsement', 'clause_in_instrument_on_other_subject', 'court_or_regulatory_order', 'procurement_standard',)),
    'core.governance_direction': ('f84d7bfb555ec9856b9d13f4b269dfedd31b070fd148dc5a93b30b8c4fd38149', ('prohibits', 'restricts_with_conditions', 'permits', 'requires', 'promotes',)),
    'core.service_domain': ('123bf211ef3127c9998ee9064714c651171f1a284832af21f9c117c6ecdb8150', ('general_public_services', 'defence', 'public_order_safety', 'economic_affairs', 'environmental_protection', 'housing_community_amenities', 'health', 'recreation_culture_religion', 'education', 'social_protection', 'other',)),
    'core.genai_mechanism_basis': ('c23be1bdd952944f28000538057031619e40ec02d05d4445e2a57644a7480cdd', ('named_genai_product_or_model', 'explicit_genai_label', 'generative_capability_described', 'ai_chatbot_or_assistant_label_only', 'no_generative_signal',)),
    'core.deployment_scale_unit': ('87368e214a3f451255e7ecf7d61518e8642043fce8097e9299abcbfc9994d55b', ('licences_or_seats', 'users', 'interactions', 'units_or_departments', 'none',)),
    'core.has_human_oversight': ('f457c8145acede1568adb8b4935f40c6ec54f1527e86afb4de1fcfb0bbc7e614', ('yes', 'no', 'unclear',)),
    'core.has_transparency_notice': ('1feb9b1b0a856b2230f82f423887235fa54e5e5639cc0fea2e740ea24e31accb', ('yes', 'no', 'unclear',)),
    'core.has_data_classification': ('7f4298c0a9d34091bdff171a97ab9d0a143b74439e2a7354c756d7d955111bd2', ('yes', 'no', 'unclear',)),
    'core.has_risk_assessment': ('6b438e33e59995ecb695bcbde885caee7d2bea00896ac8832eb4342638b0dace', ('yes', 'no', 'unclear',)),
    'core.outcome_kind': ('59564af9fc5b525d9472d8ed39d46328708e5f8768eade74b8f57edb7b3aaacc', ('quantified', 'qualitative', 'none_reported',)),
    'core.incident_kind': ('0f4afe6e02b0cd70050442ee5f46ecef32fb1aa645bdf3832b2a076deebfed66', ('quantified', 'qualitative', 'none_reported', 'discontinuation_uncertain',)),
    'core.evaluation_documented': ('04b649f49a72fd77cbec33e3669e421e7153302044dab5fe06ec6878eff0a0ee', ('results_reported', 'conducted_no_results', 'required_or_planned', 'unclear',)),
    'core.evaluation_type_pre_deployment_testing': ('c3706c6d9bebdf6e901dc45dce655bbb948818fd9883ad5bf64ea58eaa7076a5', ('yes', 'no',)),
    'core.evaluation_type_pilot_evaluation': ('1099159d5be8b73c936cf133d62882c92b016ba20959f5eb29a124fbf02f5796', ('yes', 'no',)),
    'core.evaluation_type_independent_audit': ('e0766d1413eca8d14e85c1e33b0b6605f3bef4b81795fded86c169ee7a0ceedb', ('yes', 'no',)),
    'core.evaluation_type_ongoing_monitoring': ('71286dc8612e46e34aaf558f5927e29a38add37c5720508ac8f122e7d95bf290', ('yes', 'no',)),
    'core.evaluation_type_user_feedback': ('dea28705e59122ac47606e82ec2a32a190ef8ed19a8272c91ed2f8e280f675dc', ('yes', 'no',)),
    'core.evaluation_type_bias_or_safety_testing': ('b1d0421cf3637b33abd41b5a668afff5cb9352b61c14e809e26aca6c6d877fc2', ('yes', 'no',)),
    'core.stage_as_of_basis': ('c4b647d7928f513a6a95f9d65e11fd351d23b597e78d12fed5a731cd9783d3d7', ('publication', 'stated', 'access',)),
    'core.permanent_pilot': ('2c15465e82f9f7f3ea29dfce9ac4cb3f9f0629345bf9880d12dfebfe45a46748', ('yes', 'no',)),
    'core.support_entailment': ('6607e989006ecf017caa1f2fd23f2b5f30b9adbeefbed96b22d7d4d09c3e6127', ('true', 'false',)),
    'core.activity_relation_cross_page': ('f065c023f39a30eb1e9e1e89d0eb8f96ab60ebfa902a5de7c69abc0f1c6d7691', ('same_activity', 'component_of_program', 'has_component', 'shared_participation', 'governs', 'governed_by', 'distinct_action', 'unresolved',)),
    'core.observed_actor_role': ('810963929241da559892fb090d147f5ce543f0a47569f9503b7bcd4c0a79d208', ('institutional_actor', 'issuer', 'participant', 'external_speaker', 'service_provider', 'event_host',)),
    'core.support_status_second_reason': ('789e41d0caa0aa77d9911763f463a01683c667b3f7c1cf1e233910eb832938ac', ('downgraded_no_quote', 'downgraded_low_confidence', 'downgraded_quote_not_stating_value',)),
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
STAGE_AS_OF_BASIS = ITEM_ENUMS['core.stage_as_of_basis'][1]  # core.stage_as_of_basis
PERMANENT_PILOT = ITEM_ENUMS['core.permanent_pilot'][1]  # core.permanent_pilot
SUPPORT_ENTAILMENT = ITEM_ENUMS['core.support_entailment'][1]  # core.support_entailment
ACTIVITY_RELATION = ITEM_ENUMS['core.activity_relation_cross_page'][1]  # core.activity_relation_cross_page
OBSERVED_ACTOR_ROLE = ITEM_ENUMS['core.observed_actor_role'][1]  # core.observed_actor_role
SUPPORT_STATUS_SECOND_REASON = ITEM_ENUMS['core.support_status_second_reason'][1]  # core.support_status_second_reason
