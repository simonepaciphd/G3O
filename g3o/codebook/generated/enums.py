# GENERATED FILE - do not edit. Built from codebook/codebook.yaml by
# g3o.codebook.generators.enums.
# codebook release: 2.7 | codebook sha256: 2ad76ee7df9da3e70fda3fe6d20fcef7b35483594b038d5446e89b1e6cce6aa7
# Intended target: T-012 enum constants (g3o/common/contract.py or a module T-012 names).
"""Codebook value lists as constants; each carries its item id and item hash."""

from __future__ import annotations

CODEBOOK_RELEASE = '2.7'
CODEBOOK_SHA256 = '2ad76ee7df9da3e70fda3fe6d20fcef7b35483594b038d5446e89b1e6cce6aa7'

#: item id -> (item hash, value codes in codebook order)
ITEM_ENUMS: dict[str, tuple[str, tuple[str, ...]]] = {
    'core.page_verdict': ('9df075bee06243aa33703279c998ffefc1413c9aa599b873e23a63fc642654c7', ('confirms_activity', 'ambiguous_genai', 'ambiguous_attribution', 'other_body', 'event_only', 'background_only', 'confirms_absence', 'no_genai', 'not_assessable',)),
    'core.disclosure_form': ('6d5ce44a18eea9599e585257ed852f2bf73a412c1de68bd3c8ef7ec1dde80256', ('register_cross_institution', 'register_single_institution', 'mandated_report', 'formal_record', 'informal_official', 'third_party',)),
    'core.disclosure_scope': ('089514643eaca8c94b06d0d617c2082f6604ef19a8f6c3680be56860fe8143b2', ('whole_of_government', 'multi_institution', 'single_institution',)),
    'core.page_complete': ('51ca906f401a602a318eafdc8bca73eeabd5de58da3e0cdec44c9c2f7841333a', ('yes', 'no',)),
    'core.source_type': ('eeec6e92b28743e0e64973fc7847010727a12a4b47d0cefcb38ab7ada9a7e5c0', ('news_major', 'news_trade', 'vendor', 'academic', 'policy_org', 'social_media', 'procurement_tender', 'other',)),
    'core.content_contact_named': ('3e327f7b4ad6a742e2d7d7c655b8b25f50302d223b1df2100286192abd22f138', ('yes', 'no',)),
    'core.content_contact_details': ('fc7ef02ed1ceea6bb837c625ea62bf0b83476213e30ff90785b7b89e7391a804', ('yes', 'no',)),
    'core.content_data': ('861eaa4fb096f613b15b17416a5f16106f231f0cb0015554dcb5de27000cfeb4', ('yes', 'no',)),
    'core.activity_segment': ('e985ba404a1c1c70fd6b505b35736fde02c737251ea40e83dda2ec3fb7cd3759', ('same_activity', 'component_of_program', 'has_component', 'shared_participation', 'governs', 'governed_by', 'distinct_action', 'unresolved', 'not_an_activity',)),
    'core.observed_actor_relationship': ('eb128ea7cd4da3523104479bb645e543c69c729fa6164d14f6cce3607ed271b7', ('this_institution', 'unit_of_institution', 'joint_participant', 'other', 'unresolved',)),
    'core.activity_type': ('9ab6d6db8652f2aa46c2b9652e86594bb411b52cd20b3b41bc338b8e3466abf0', ('policy_guidance', 'pilot_experiment', 'program_initiative', 'internal_operational', 'public_facing_service',)),
    'core.action_type': ('ece42341264b8bebbd0599788bc5dc0606c3d10a7652299c2248acb4785db3b6', ('deployment', 'governance', 'staff_training', 'program',)),
    'core.adoption_stage': ('c2c162b7663483a48c5364418a9887c3f2204fa1d706f9b0b25a6b52865e4bb4', ('proposed', 'announced', 'pilot', 'production', 'discontinued',)),
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
    'core.deployment_mode': ('7da7a90e15a99e1ecdfe1290a318e2a76862a48ea53d5d8b79b26865658406b3', ('integrated', 'standalone',)),
    'core.target_users': ('8d985ade4cec6acc88a59524a2421739f44f5974d43c091cd810661c8e878675', ('internal_staff', 'public', 'both',)),
    'core.governed_population': ('0e318135188e3d9cad0912b2b6a4982b06c931ce3f329645c9c565bfa7ffb971', ('internal_personnel', 'external_users', 'both',)),
    'core.governance_form': ('ae8c86617f21eb2e92365dcaa0a538361f271d3904a56162178c17dfc4bdde44', ('dedicated_genai_or_ai_policy_or_guideline', 'approved_tool_list_or_endorsement', 'clause_in_instrument_on_other_subject', 'court_or_regulatory_order', 'procurement_standard',)),
    'core.governance_direction': ('a802ccf621f35fa12cac0de1f625aaa4b8ebecf47e1491bc6515c5dbc89816eb', ('prohibits', 'restricts_with_conditions', 'permits', 'requires', 'promotes',)),
    'core.service_domain': ('38acc164fd9dcc80757e5c7edfb714d20cb99448be913a6bb74fb56426302960', ('general_public_services', 'defence', 'public_order_safety', 'economic_affairs', 'environmental_protection', 'housing_community_amenities', 'health', 'recreation_culture_religion', 'education', 'social_protection', 'other',)),
    'core.genai_mechanism_basis': ('0f2f4e390483f9d70e2e8ed578a0a71d6ebfcc5b0874d7436e72ad424c9aeb7f', ('named_genai_product_or_model', 'explicit_genai_label', 'generative_capability_described', 'ai_chatbot_or_assistant_label_only', 'no_generative_signal',)),
    'core.deployment_scale_unit': ('c4359e7dd8e604b19a00b999b3d14d2407d5b6c8f398a8f759a417693852e7eb', ('licences_or_seats', 'users', 'interactions', 'units_or_departments', 'none',)),
    'core.has_human_oversight': ('d295f72c1b7d9084ba2aaa7175f0d072bd1847acd66828f5764b3109c9406d40', ('yes', 'no', 'unclear',)),
    'core.has_transparency_notice': ('8b67314da88223d5cb70d2f9a20264670f1db2aacdc58287238d97c3161b1f0c', ('yes', 'no', 'unclear',)),
    'core.has_data_classification': ('c87240d8603e964e338ee2429213041510bf66932774798e63a0063945a4fdfc', ('yes', 'no', 'unclear',)),
    'core.has_risk_assessment': ('4b340b3af9416bb9713e92e6558919763d64617c523fb4bbc5e633f149358ea4', ('yes', 'no', 'unclear',)),
    'core.outcome_kind': ('7215b6b2576b8a967c86362ed2a3d4dbcb740b84a4f23d2de05a4ef817091e12', ('quantified', 'qualitative', 'none_reported',)),
    'core.incident_kind': ('9d7ab9101539f801ee5098e8df2c46e9f0b6fcc27fdf679eaf88cf502f395d32', ('quantified', 'qualitative', 'none_reported', 'discontinuation_uncertain',)),
    'core.evaluation_documented': ('72612246f3249a9de830061aaea503805790864a71a345b04c7cc9cd94afa366', ('results_reported', 'conducted_no_results', 'required_or_planned', 'unclear',)),
    'core.evaluation_type_pre_deployment_testing': ('56f266691b0a497adc3ae6c663c7c888f3af1cea40395e6c164da02b6059182a', ('yes', 'no',)),
    'core.evaluation_type_pilot_evaluation': ('908c2704cf1af68a2036806c821a047e91bbf3135830238a2e7546037a05f3cd', ('yes', 'no',)),
    'core.evaluation_type_independent_audit': ('1f17899a3484b6ac7bc35b61cf459bd84e0c0cc5efe52a1f33facd11eab0c5b7', ('yes', 'no',)),
    'core.evaluation_type_ongoing_monitoring': ('781f24c150accde0fd605d3066e4f8cb79dc91b971b656669a75abc26a9092d8', ('yes', 'no',)),
    'core.evaluation_type_user_feedback': ('f6254ba80055d4ba6ff7051f9c1fda8436849aa1abaa9cce14741863912b63b1', ('yes', 'no',)),
    'core.evaluation_type_bias_or_safety_testing': ('c0ae0fc3fbd69f6159a885ad4f9638f66cde52f394cd20a36b2ee7ca896a466e', ('yes', 'no',)),
    'core.stage_as_of_basis': ('c40ce46095c40201d4c252d58c6eaa6fa915a8ae19e1a4fe3abe01f314c3c953', ('publication', 'stated', 'access',)),
    'core.permanent_pilot': ('152bbabb24b057f88773d735097cc0341ee6e95603be4597682f789458beedb2', ('yes', 'no',)),
    'core.support_entailment': ('adde7fa704c82447caec3af45cd3330e8942dc90b2da70c56fad0a0f76954d0d', ('true', 'false',)),
    'core.activity_relation_cross_page': ('ace0da2bc93b3c6a70f0a97873b123abea5906bba93b238f926feff086ed6e5c', ('same_activity', 'component_of_program', 'has_component', 'shared_participation', 'governs', 'governed_by', 'distinct_action', 'unresolved',)),
    'core.observed_actor_role': ('49db2543e6a85f2373dcd89d14185927a46b9f9eea29ecebb4c686d8d89faf66', ('institutional_actor', 'issuer', 'participant', 'external_speaker', 'service_provider', 'event_host',)),
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
STAGE_AS_OF_BASIS = ITEM_ENUMS['core.stage_as_of_basis'][1]  # core.stage_as_of_basis
PERMANENT_PILOT = ITEM_ENUMS['core.permanent_pilot'][1]  # core.permanent_pilot
SUPPORT_ENTAILMENT = ITEM_ENUMS['core.support_entailment'][1]  # core.support_entailment
ACTIVITY_RELATION = ITEM_ENUMS['core.activity_relation_cross_page'][1]  # core.activity_relation_cross_page
OBSERVED_ACTOR_ROLE = ITEM_ENUMS['core.observed_actor_role'][1]  # core.observed_actor_role
SUPPORT_STATUS_SECOND_REASON = ITEM_ENUMS['core.support_status_second_reason'][1]  # core.support_status_second_reason
