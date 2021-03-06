from core.terraform.resources.aws.aws_lambda import LambdaFunctionResource, LambdaPermission
from core.terraform.resources.aws.cloudwatch import CloudWatchEventRuleResource, CloudWatchEventTargetResource
from core.terraform.resources.variable import TerraformVariable
from resources.datastore.es import ESDomain
from resources.iam.lambda_role import LambdaRole
from resources.s3.bucket import BucketStorage
from resources.batch.job import SubmitAndRuleEngineJobDefinition, RuleEngineJobQueue
from resources.data.aws_info import AwsAccount, AwsRegion
from resources.lambda_rule_engine.s3_upload import UploadLambdaRuleEngineZipFile, RULE_ENGINE_JOB_FILE_NAME
from resources.lambda_rule_engine.utils import get_rule_engine_cloudwatch_rules_var
from core.config import Settings
from core.providers.aws.boto3 import cloudwatch_event


class RuleEngineLambdaFunction(LambdaFunctionResource):
    function_name = "ruleengine"
    role = LambdaRole.get_output_attr('arn')
    handler = RULE_ENGINE_JOB_FILE_NAME + ".lambda_handler"
    runtime = "python2.7"
    s3_bucket = BucketStorage.get_output_attr('bucket')
    s3_key = UploadLambdaRuleEngineZipFile.get_output_attr('id')
    environment = {
        'variables': {
            'JOB_QUEUE': RuleEngineJobQueue.get_input_attr('name'),
            'JOB_DEFINITION': SubmitAndRuleEngineJobDefinition.get_input_attr('name')
        }
    }

    DEPENDS_ON = [SubmitAndRuleEngineJobDefinition, RuleEngineJobQueue]


class RulesListVariable(TerraformVariable):
    variable_name = "rules"
    variable_type = "list"
    default_value = []
    variable_dict_input = get_rule_engine_cloudwatch_rules_var()


class RuleEngineEventRules(CloudWatchEventRuleResource):
    count = RulesListVariable.length()
    name = RulesListVariable.lookup('ruleId')
    schedule_expression = RulesListVariable.lookup('schedule')

    VARIABLES = [RulesListVariable]
    DEPENDS_ON = [RuleEngineLambdaFunction]
    available_args = {
        'name': {'required': True},
        'schedule_expression': {'required': True},
        'event_pattern': {'required': False},
        'role_arn ': {'required': False},
        'is_enabled ': {'required': False},
        'description': {'required': False}
    }

    def check_exists_before(self, input, tf_outputs):
        exists = False
        checked_details = {}

        if not self.resource_in_tf_output(tf_outputs):
            for rule in get_rule_engine_cloudwatch_rules_var():
                rule_name = rule['ruleId']
                exists = cloudwatch_event.check_rule_exists(
                    rule_name,
                    input.aws_access_key,
                    input.aws_secret_key,
                    input.aws_region)

                if exists:
                    checked_details = {'attr': "name", 'value': rule_name}
                    break

        return exists, checked_details


class RuleEngineCloudWatchEventTargets(CloudWatchEventTargetResource):
    count = RulesListVariable.length()
    rule = RulesListVariable.lookup('ruleId')
    arn = RuleEngineLambdaFunction.get_output_attr('arn')
    target_id = RuleEngineLambdaFunction.get_input_attr('function_name') + '-target'
    target_input = RulesListVariable.lookup('ruleParams')

    DEPENDS_ON = [RuleEngineEventRules]


class EventRulesLambdaPermissions(LambdaPermission):
    statement_id = "sid-" + Settings.AWS_ACCOUNT_ID
    action = "lambda:InvokeFunction"
    function_name = RuleEngineLambdaFunction.get_output_attr('function_name')
    principal = "events.amazonaws.com"
    # source_arn = RuleEngineEventRules.get_output_attr(key='arn', index=True) #Not required since there are huge list of rules

    DEPENDS_ON = [RuleEngineCloudWatchEventTargets]
