"""
CloudFront WAF Stack - MUST be deployed to us-east-1.

WAFv2 Web ACLs with scope=CLOUDFRONT are a global resource that AWS requires
to be created in us-east-1 regardless of the deployment region of the rest of
the application.

This stack is intentionally pinned to us-east-1 and:
  1. Creates the WAF Web ACL (scope=CLOUDFRONT).
  2. Publishes the ARN to SSM Parameter Store in us-east-1.
  3. Exposes ``get_web_acl_arn_for(scope)`` – call this from any other stack
     to receive a resolved WAF ARN token.  The method transparently performs
     a cross-region SSM lookup when the calling stack lives outside us-east-1,
     so callers never need to write region-conditional code.
"""

from typing import Optional, List

import aws_cdk as cdk
from aws_cdk import (
    aws_wafv2 as waf,
    aws_ssm as ssm,
    custom_resources as cr,
)
from constructs import Construct

from stacks.common.constants import WAF_METRIC_NAME_PREFIX

# SSM parameter path used to share the WAF ARN across regions/stacks.
_WAF_ARN_SSM_PARAM = "/{project_name}/cloudfront-waf-arn"


def get_waf_ssm_param_name(project_name: str) -> str:
    """Return the SSM parameter path used to share the WAF ARN cross-region."""
    return _WAF_ARN_SSM_PARAM.format(project_name=project_name)


class CloudFrontWAFStack(cdk.Stack):
    """
    Dedicated stack for the CloudFront WAF Web ACL.

    Always deployed to us-east-1 (AWS platform constraint).  Callers obtain
    a resolved WAF ARN by calling ``get_web_acl_arn_for(scope)`` from within
    their own stack – no region-conditional logic required.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str,
        prefix_lists: Optional[List[str]] = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault(
            "description",
            (
                "CloudFront WAF Web ACL (us-east-1 global resource) "
                "for multi-agent AI orchestration UI - (Solution ID - SO9637)"
            ),
        )
        super().__init__(scope, construct_id, **kwargs)

        self.project_name = project_name
        self.prefix_lists = prefix_lists or []
        self._ssm_param_name = get_waf_ssm_param_name(project_name)

        # Create the WAF Web ACL with scope=CLOUDFRONT (us-east-1 only)
        self._web_acl = self._create_web_acl()

        # Store the ARN for same-region consumers and cross-region lookups
        self._web_acl_arn: str = self._web_acl.attr_arn

        # Publish ARN to SSM so cross-region consumers can retrieve it
        ssm.StringParameter(
            self,
            "CloudFrontWAFArnParam",
            parameter_name=self._ssm_param_name,
            string_value=self._web_acl_arn,
            description=(
                f"ARN of the CloudFront WAF Web ACL for project {project_name}. "
                "Retrieved cross-region by the UI stack via SSM lookup."
            ),
            tier=ssm.ParameterTier.STANDARD,
        )

        cdk.CfnOutput(
            self,
            "CloudFrontWAFArn",
            value=self._web_acl_arn,
            description="ARN of the CloudFront WAF Web ACL",
            export_name=f"{project_name}-CloudFrontWAFArn",
        )

    def get_web_acl_arn_for(self, calling_scope: Construct) -> str:
        """
        Return a resolved WAF ARN token usable from ``calling_scope``'s stack.

        When the calling stack is in the same region as this stack (us-east-1),
        the CDK token for the ARN is returned directly – no extra resources.

        When the calling stack is in a different region, a CloudFormation
        Custom Resource is created *inside the calling stack* to look up the
        ARN from SSM Parameter Store in us-east-1 at deploy time.  This keeps
        all cross-region plumbing encapsulated here; callers remain
        region-agnostic.

        Args:
            calling_scope: Any CDK construct inside the stack that needs the ARN.

        Returns:
            A string token that resolves to the WAF ARN at deploy time.
        """
        calling_stack = cdk.Stack.of(calling_scope)
        calling_region = calling_stack.region

        # Same region (us-east-1): return token directly, no lookup needed.
        if calling_region == "us-east-1" or cdk.Token.is_unresolved(calling_region):
            return self._web_acl_arn

        # Different region: create a custom resource inside the calling stack
        # that reads the SSM parameter from us-east-1 at deploy time.
        # Use a stable logical ID so CDK doesn't recreate it on every synth.
        lookup_id = "CloudFrontWAFArnCrossRegionLookup"
        existing = calling_stack.node.try_find_child(lookup_id)
        if existing:
            # Reuse if already created (e.g. multiple constructs in same stack)
            return existing.get_response_field("Parameter.Value")

        lookup = cr.AwsCustomResource(
            calling_stack,
            lookup_id,
            on_create=cr.AwsSdkCall(
                service="SSM",
                action="getParameter",
                parameters={"Name": self._ssm_param_name},
                region="us-east-1",  # Always read from us-east-1
                physical_resource_id=cr.PhysicalResourceId.of(
                    f"{self.project_name}-waf-arn-ssm-lookup"
                ),
            ),
            on_update=cr.AwsSdkCall(
                service="SSM",
                action="getParameter",
                parameters={"Name": self._ssm_param_name},
                region="us-east-1",
                physical_resource_id=cr.PhysicalResourceId.of(
                    f"{self.project_name}-waf-arn-ssm-lookup"
                ),
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE
            ),
        )

        return lookup.get_response_field("Parameter.Value")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_web_acl(self) -> waf.CfnWebACL:
        """Build the WAF Web ACL with OWASP Common Rule Set."""
        waf_metric_name = f"{self.project_name}-{WAF_METRIC_NAME_PREFIX}-cloudfront"
        rules: List[waf.CfnWebACL.RuleProperty] = []
        priority = 0

        # Optional IP allow-list rule derived from VPC prefix lists
        if self.prefix_lists:
            ip_set = waf.CfnIPSet(
                self,
                "CloudFrontIPSet",
                scope="CLOUDFRONT",
                ip_address_version="IPV4",
                addresses=self._resolve_prefix_list_cidrs(),
                name=f"{self.project_name}-cloudfront-allowed-ips",
            )
            rules.append(
                waf.CfnWebACL.RuleProperty(
                    name="IPWhitelistRule",
                    priority=priority,
                    statement=waf.CfnWebACL.StatementProperty(
                        ip_set_reference_statement=waf.CfnWebACL.IPSetReferenceStatementProperty(
                            arn=ip_set.attr_arn
                        )
                    ),
                    action=waf.CfnWebACL.RuleActionProperty(allow={}),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name=f"{waf_metric_name}-ip-whitelist",
                        sampled_requests_enabled=True,
                    ),
                )
            )
            priority += 1

        # OWASP Common Rule Set – always present
        rules.append(
            waf.CfnWebACL.RuleProperty(
                name="OWASPRuleSet",
                priority=priority,
                statement=waf.CfnWebACL.StatementProperty(
                    managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                        vendor_name="AWS",
                        name="AWSManagedRulesCommonRuleSet",
                    )
                ),
                override_action=waf.CfnWebACL.OverrideActionProperty(none={}),
                visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True,
                    metric_name=f"{waf_metric_name}-owasp",
                    sampled_requests_enabled=True,
                ),
            )
        )

        default_action = (
            waf.CfnWebACL.DefaultActionProperty(block={})
            if self.prefix_lists
            else waf.CfnWebACL.DefaultActionProperty(allow={})
        )

        return waf.CfnWebACL(
            self,
            "CloudFrontWAF",
            default_action=default_action,
            scope="CLOUDFRONT",
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name=waf_metric_name,
                sampled_requests_enabled=True,
            ),
            rules=rules,
        )

    def _resolve_prefix_list_cidrs(self) -> List[str]:
        """
        Resolve AWS managed prefix list IDs to CIDR blocks via custom resources.

        Returns:
            List of CIDR strings resolved from configured prefix lists.
        """
        all_cidrs: List[str] = []

        for i, prefix_list_id in enumerate(self.prefix_lists):
            cidr_lookup = cr.AwsCustomResource(
                self,
                f"PrefixListCidrLookup{i}",
                on_create=cr.AwsSdkCall(
                    service="EC2",
                    action="getManagedPrefixListEntries",
                    parameters={"PrefixListId": prefix_list_id},
                    physical_resource_id=cr.PhysicalResourceId.of(
                        f"prefix-list-cidr-lookup-{i}"
                    ),
                ),
                policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                    resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE
                ),
            )

            for entry_index in range(2):
                try:
                    cidr = cidr_lookup.get_response_field(f"Entries.{entry_index}.Cidr")
                    all_cidrs.append(cidr)
                except Exception:
                    break  # No more entries for this prefix list

        if not all_cidrs:
            raise ValueError(
                f"Failed to resolve any CIDR blocks from prefix lists: {self.prefix_lists}"
            )

        return all_cidrs
