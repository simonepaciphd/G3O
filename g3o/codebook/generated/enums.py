# GENERATED FILE - do not edit. Built from codebook/codebook.yaml by
# g3o.codebook.generators.enums.
# codebook release: 2.7 | codebook sha256: 3692c06a77056c43285b2696fa9d1aea1e733290fbd977976f40c6426803859a
# Intended target: T-012 enum constants (g3o/common/contract.py or a module T-012 names).
"""Codebook value lists as constants; each carries its item id and item hash."""

from __future__ import annotations

CODEBOOK_RELEASE = '2.7'
CODEBOOK_SHA256 = '3692c06a77056c43285b2696fa9d1aea1e733290fbd977976f40c6426803859a'

#: item id -> (item hash, value codes in codebook order)
ITEM_ENUMS: dict[str, tuple[str, tuple[str, ...]]] = {
    'core.page_verdict': ('53d840f9ce15ea57ca95baa99302d6b50708cb6c2de77d7971881030f2747b44', ('confirms_activity', 'ambiguous_genai', 'ambiguous_attribution', 'other_body', 'event_only', 'background_only', 'confirms_absence', 'no_genai', 'not_assessable',)),
    'core.disclosure_form': ('6d5ce44a18eea9599e585257ed852f2bf73a412c1de68bd3c8ef7ec1dde80256', ('register_cross_institution', 'register_single_institution', 'mandated_report', 'formal_record', 'informal_official', 'third_party',)),
    'core.disclosure_scope': ('089514643eaca8c94b06d0d617c2082f6604ef19a8f6c3680be56860fe8143b2', ('whole_of_government', 'multi_institution', 'single_institution',)),
    'core.page_complete': ('0125217cda0f3b064a80821fd9ae31c1fa5fb158dc73ead1c3d95be09379f503', ('yes', 'no',)),
    'core.source_type': ('eeec6e92b28743e0e64973fc7847010727a12a4b47d0cefcb38ab7ada9a7e5c0', ('news_major', 'news_trade', 'vendor', 'academic', 'policy_org', 'social_media', 'procurement_tender', 'other',)),
    'core.content_contact_named': ('b4589c821abd21e0a49357bf82144bcd2b8cf3d855cfef37b73dcf9e68455312', ('yes', 'no',)),
    'core.content_contact_details': ('f48276daef2a6c61dab279f0cc18134ae65dce1710dd788428c3fe85282df5af', ('yes', 'no',)),
    'core.content_data': ('873afed104d45718bd358c1d669cfafa141d7f93933ccb9eebfa61098d5811cb', ('yes', 'no',)),
    'core.activity_segment': ('e985ba404a1c1c70fd6b505b35736fde02c737251ea40e83dda2ec3fb7cd3759', ('same_activity', 'component_of_program', 'has_component', 'shared_participation', 'governs', 'governed_by', 'distinct_action', 'unresolved', 'not_an_activity',)),
    'core.observed_actor_relationship': ('eb128ea7cd4da3523104479bb645e543c69c729fa6164d14f6cce3607ed271b7', ('this_institution', 'unit_of_institution', 'joint_participant', 'other', 'unresolved',)),
    'core.activity_type': ('5c28210b54b5c1510bff389b9e4949d8b009be0e4ad6623263f248c567d424db', ('policy_guidance', 'pilot_experiment', 'program_initiative', 'internal_operational', 'public_facing_service',)),
    'core.action_type': ('bfe28f4947f246600468c1a6587f739518ef7a5e6771733389a6fbbcfb5b81ce', ('deployment', 'governance', 'staff_training', 'program',)),
    'core.adoption_stage': ('3c9a80bba2641f0192a3812d0281bb44469e5efffe698f13b8f7117dc6939c6f', ('proposed', 'announced', 'pilot', 'production', 'discontinued',)),
    'core.procurement_status': ('069cac4eae165dba976c259f3d778a07c2a07fe9ff5d88f60f780c501519af39', ('none_documented', 'tender_or_rfp', 'award_or_contract', 'payment_or_subscription',)),
    'core.model_origin': ('604814a8eeb44403f59c7eb1c3dd321e8618344ef2c7492918e0dfb91e38084f', ('commercial', 'open_weight', 'government_developed',)),
    'core.build_arrangement': ('26747e9b192f65d107fefbb46c7423d785b554a37936e2dd775eee596ecfc205', ('off_the_shelf_product', 'custom_application_on_external_model', 'model_trained_or_fine_tuned_by_institution',)),
    'core.interface': ('1f6053a45c6b23423f842cf6f7298ebec811773fa4dab7c930493f3dc4ffdb52', ('conversational', 'backend_or_api', 'other_interface',)),
    'core.function_drafting_writing': ('a053690516ee898f1bdff22da452ed5f433f2372b5533f9dfbb6b9ea8ad338fe', ('yes', 'no',)),
    'core.function_summarization': ('edfbd403f224c2df70919e51689a7ec36b3dbb599872860118adb077153dffb4', ('yes', 'no',)),
    'core.function_translation': ('872277e5bf01ebeae5c7651032d8a86a71c71a8e79373466d23bb3e22ac470ed', ('yes', 'no',)),
    'core.function_search_retrieval': ('24d3e6c6e7c999d5ea25cf87318eb9aee07a7300048ebc8a9c027a89f53e285b', ('yes', 'no',)),
    'core.function_code': ('ab11951183a0b10e3b61f8d61d1b0d37e3b3e973fe211d739cffe02798edcc08', ('yes', 'no',)),
    'core.function_image_audio_video': ('538dff367d93a589aa7561b3306a2bb3fddded3f6655ae9478ecc57e42b2c242', ('yes', 'no',)),
    'core.function_extraction_classification': ('c6b8d591da62fc1af2e39bd85f12bc2a27e423a2e24ff8f4441bdeef4c03fc6f', ('yes', 'no',)),
    'core.function_analysis_recommendation': ('46e598ead1d140774354594de96cc8e910dc942454798338b0535efc6c39dc4b', ('yes', 'no',)),
    'core.deployment_mode': ('b98e0a21cf8e6214df70fb55b4d1c07d269ccb33edb7018f6d942abbb9a0602c', ('integrated', 'standalone',)),
    'core.target_users': ('34d84236cf9dff00347f35585a18556f9861c83aa4578d8104e9d84821514d94', ('internal_staff', 'public', 'both',)),
    'core.governed_population': ('a786dcbf8d250e7bd267a110a2fb65ae851fe1f5c33c863002e96563dd3ed430', ('internal_personnel', 'external_users', 'both',)),
    'core.governance_form': ('49492f6cc3240e7b05bb438a5869d24e4e30904ac281d54ddf0ffbb235cc3717', ('dedicated_genai_or_ai_policy_or_guideline', 'approved_tool_list_or_endorsement', 'clause_in_instrument_on_other_subject', 'court_or_regulatory_order', 'procurement_standard',)),
    'core.governance_direction': ('447d9f41a426d6b143bd16c4149cb67d7b94321a1cf583c7563f7f07958d3d54', ('prohibits', 'restricts_with_conditions', 'permits', 'requires', 'promotes',)),
    'core.service_domain': ('6d4627193be4485e52d5ceaa662c7d109d39035a481c91c4da0440bb560ba7a3', ('general_public_services', 'defence', 'public_order_safety', 'economic_affairs', 'environmental_protection', 'housing_community_amenities', 'health', 'recreation_culture_religion', 'education', 'social_protection', 'other',)),
    'core.genai_mechanism_basis': ('de94ee8e9e42e7a6d0ed45e30260dad5d3be1c15b4b7b07b5bef3ca54331c837', ('named_genai_product_or_model', 'explicit_genai_label', 'generative_capability_described', 'ai_chatbot_or_assistant_label_only',)),
    'core.deployment_scale_unit': ('c4359e7dd8e604b19a00b999b3d14d2407d5b6c8f398a8f759a417693852e7eb', ('licences_or_seats', 'users', 'interactions', 'units_or_departments', 'none',)),
    'core.has_human_oversight': ('2baab3c1c2c4a87916acd613ef01aa56ccbaddeb739f920c793a649e9b2b839f', ('yes', 'no', 'unclear',)),
    'core.has_transparency_notice': ('bcefdc276e698be877c13588df80ffcddac8e3542453155ea2e770133a865883', ('yes', 'no', 'unclear',)),
    'core.has_data_classification': ('ba98b2d241f40f7137c626e7e7c0ad41c0b87581fc538d6f4caf1813bcd3cd59', ('yes', 'no', 'unclear',)),
    'core.has_risk_assessment': ('4b340b3af9416bb9713e92e6558919763d64617c523fb4bbc5e633f149358ea4', ('yes', 'no', 'unclear',)),
    'core.outcome_kind': ('7215b6b2576b8a967c86362ed2a3d4dbcb740b84a4f23d2de05a4ef817091e12', ('quantified', 'qualitative', 'none_reported',)),
    'core.incident_kind': ('9d7ab9101539f801ee5098e8df2c46e9f0b6fcc27fdf679eaf88cf502f395d32', ('quantified', 'qualitative', 'none_reported', 'discontinuation_uncertain',)),
    'core.evaluation_documented': ('8d878b747de11b7e8f8888b27a5c568da0cbb4c47c235026f47bf282eb59dd0b', ('results_reported', 'conducted_no_results', 'required_or_planned', 'unclear',)),
    'core.evaluation_type_pre_deployment_testing': ('1a10522c420a29a7d32380d7cd01a05b93f079ad16a86ab5363abf1b00bd57b5', ('yes', 'no',)),
    'core.evaluation_type_pilot_evaluation': ('f001133a064ea6b3506d862a263b2209ae2ccc92e432aa96016b22bba68ed7d9', ('yes', 'no',)),
    'core.evaluation_type_independent_audit': ('a57820efa0471b8418a1e189d36436db00daec4a7addd6ce7ebd197933157cdc', ('yes', 'no',)),
    'core.evaluation_type_ongoing_monitoring': ('864d35832b2dc6bea2f69a060359f1ef12cee317ed7a7fc24d0b531a46400d72', ('yes', 'no',)),
    'core.evaluation_type_user_feedback': ('9628c4f69ed51033eddcdb1434bc8f26d0acc10af1d764282cc8aff9748ddd6f', ('yes', 'no',)),
    'core.evaluation_type_bias_or_safety_testing': ('705995787c3a7371a35e78397796bc50ee46fd60ad7d73609bd62bbdc5d8c35f', ('yes', 'no',)),
    'core.support_entailment': ('6156631ceb19770919ed6792092f3169bb7442317702b6fb1fbfe76d26a6b172', ('true', 'false',)),
    'core.activity_relation_cross_page': ('ace0da2bc93b3c6a70f0a97873b123abea5906bba93b238f926feff086ed6e5c', ('same_activity', 'component_of_program', 'has_component', 'shared_participation', 'governs', 'governed_by', 'distinct_action', 'unresolved',)),
    'core.observed_actor_role': ('47c6b173d8d672bffc766f9603b797b24a136c418aebb5be2c4a0a0c236d93fc', ('institutional_actor', 'issuer', 'participant', 'external_speaker', 'service_provider', 'event_host',)),
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
