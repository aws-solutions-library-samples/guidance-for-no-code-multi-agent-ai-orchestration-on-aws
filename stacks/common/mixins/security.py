"""Security group mixin for CDK stacks."""

from typing import List, Optional

from aws_cdk import aws_ec2 as ec2

from ..validators import ConfigValidator


class SecurityGroupMixin:
    """
    Mixin class providing security group functionality.
    
    This mixin provides methods for creating and managing security groups
    with proper validation and best practices.
    """
    
    def create_vpc_lattice_security_group(self,
                                          name: str,
                                          vpc: ec2.Vpc,
                                          port: int,
                                          region: str,
                                          description: Optional[str] = None) -> ec2.SecurityGroup:
        """
        Create a security group configured for VPC Lattice.
        
        Args:
            name: Name for the security group
            vpc: VPC to create the security group in
            port: Port to allow traffic on
            region: AWS region for prefix list lookup
            description: Optional description for the security group
            
        Returns:
            The created security group
        """
        # Validate inputs
        ConfigValidator.validate_resource_name(name)
        ConfigValidator.validate_port_range(port)
        
        security_group = ec2.SecurityGroup(
            self, 
            f"{name}-security-group",
            vpc=vpc,
            description=description or f"Security group for {name}",
            allow_all_outbound=True
        )
        
        try:
            # Look up VPC Lattice prefix list
            vpc_lattice_prefix_list = ec2.PrefixList.from_lookup(
                self,
                f"{name}-vpc-lattice-prefix-list",
                prefix_list_name=f"com.amazonaws.{region}.vpc-lattice"
            )
            
            # Allow ingress from VPC Lattice prefix list
            security_group.add_ingress_rule(
                peer=ec2.Peer.prefix_list(vpc_lattice_prefix_list.prefix_list_id),
                connection=ec2.Port.tcp(port),
                description="Allow HTTP from VPC Lattice"
            )
            
            # Allow health check traffic from VPC Lattice prefix list
            security_group.add_ingress_rule(
                peer=ec2.Peer.prefix_list(vpc_lattice_prefix_list.prefix_list_id),
                connection=ec2.Port.tcp(port),
                description="Allow health check from VPC Lattice"
            )
            
        except Exception:
            # Fallback to allowing from VPC CIDR if prefix list not found
            pass
        
        # Allow direct VPC access as fallback
        security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(port),
            description="Allow HTTP from VPC CIDR"
        )
        
        return security_group
    
    def create_web_security_group(self,
                                  name: str,
                                  vpc: ec2.Vpc,
                                  allowed_cidrs: List[str] = None,
                                  description: Optional[str] = None) -> ec2.SecurityGroup:
        """
        Create a security group for web applications.
        
        Args:
            name: Name for the security group
            vpc: VPC to create the security group in
            allowed_cidrs: List of CIDR blocks to allow HTTP/HTTPS from
            description: Optional description for the security group
            
        Returns:
            The created security group
        """
        ConfigValidator.validate_resource_name(name)
        
        if allowed_cidrs:
            for cidr in allowed_cidrs:
                ConfigValidator.validate_cidr_block(cidr)
        
        security_group = ec2.SecurityGroup(
            self,
            f"{name}-web-security-group", 
            vpc=vpc,
            description=description or f"Web security group for {name}",
            allow_all_outbound=True
        )
        
        # Default to allowing from anywhere if no CIDRs specified
        source_cidrs = allowed_cidrs or ["0.0.0.0/0"]
        
        for cidr in source_cidrs:
            # Allow HTTP
            security_group.add_ingress_rule(
                peer=ec2.Peer.ipv4(cidr),
                connection=ec2.Port.tcp(80),
                description=f"Allow HTTP from {cidr}"
            )
            
            # Allow HTTPS
            security_group.add_ingress_rule(
                peer=ec2.Peer.ipv4(cidr),
                connection=ec2.Port.tcp(443),
                description=f"Allow HTTPS from {cidr}"
            )
        
        return security_group
    
    def create_database_security_group(self,
                                       name: str,
                                       vpc: ec2.Vpc,
                                       port: int,
                                       source_security_groups: List[ec2.ISecurityGroup],
                                       description: Optional[str] = None) -> ec2.SecurityGroup:
        """
        Create a security group for databases.
        
        Args:
            name: Name for the security group
            vpc: VPC to create the security group in
            port: Database port
            source_security_groups: Security groups to allow access from
            description: Optional description for the security group
            
        Returns:
            The created security group
        """
        ConfigValidator.validate_resource_name(name)
        ConfigValidator.validate_port_range(port)
        
        security_group = ec2.SecurityGroup(
            self,
            f"{name}-db-security-group",
            vpc=vpc,
            description=description or f"Database security group for {name}",
            allow_all_outbound=False  # Databases typically don't need outbound
        )
        
        # Allow access from source security groups
        for source_sg in source_security_groups:
            security_group.add_ingress_rule(
                peer=ec2.Peer.security_group_id(source_sg.security_group_id),
                connection=ec2.Port.tcp(port),
                description=f"Allow database access from {source_sg.security_group_id}"
            )
        
        return security_group
    
    def create_internal_service_security_group(self,
                                               name: str,
                                               vpc: ec2.Vpc,
                                               port: int,
                                               source_security_groups: List[ec2.ISecurityGroup] = None,
                                               description: Optional[str] = None) -> ec2.SecurityGroup:
        """
        Create a security group for internal services.
        
        Args:
            name: Name for the security group
            vpc: VPC to create the security group in
            port: Service port
            source_security_groups: Security groups to allow access from
            description: Optional description for the security group
            
        Returns:
            The created security group
        """
        ConfigValidator.validate_resource_name(name)
        ConfigValidator.validate_port_range(port)
        
        security_group = ec2.SecurityGroup(
            self,
            f"{name}-internal-security-group",
            vpc=vpc,
            description=description or f"Internal service security group for {name}",
            allow_all_outbound=True
        )
        
        if source_security_groups:
            # Allow access from specific security groups
            for source_sg in source_security_groups:
                security_group.add_ingress_rule(
                    peer=ec2.Peer.security_group_id(source_sg.security_group_id),
                    connection=ec2.Port.tcp(port),
                    description=f"Allow access from {source_sg.security_group_id}"
                )
        else:
            # Allow access from within VPC
            security_group.add_ingress_rule(
                peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
                connection=ec2.Port.tcp(port),
                description="Allow access from VPC CIDR"
            )
        
        return security_group
    
    def add_ingress_rule_with_validation(self,
                                         security_group: ec2.SecurityGroup,
                                         peer: ec2.IPeer,
                                         port: int,
                                         protocol: str = "tcp",
                                         description: Optional[str] = None) -> None:
        """
        Add an ingress rule to a security group with validation.
        
        Args:
            security_group: Security group to add rule to
            peer: Source peer for the rule
            port: Port to allow
            protocol: Protocol (tcp/udp)
            description: Optional description for the rule
        """
        ConfigValidator.validate_port_range(port)
        
        if protocol.lower() == "tcp":
            connection = ec2.Port.tcp(port)
        elif protocol.lower() == "udp":
            connection = ec2.Port.udp(port)
        else:
            raise ValueError(f"Unsupported protocol: {protocol}")
        
        security_group.add_ingress_rule(
            peer=peer,
            connection=connection,
            description=description or f"Allow {protocol.upper()} on port {port}"
        )
    
    def create_bastion_security_group(self,
                                      name: str,
                                      vpc: ec2.Vpc,
                                      allowed_ssh_cidrs: List[str],
                                      description: Optional[str] = None) -> ec2.SecurityGroup:
        """
        Create a security group for bastion hosts.
        
        Args:
            name: Name for the security group
            vpc: VPC to create the security group in
            allowed_ssh_cidrs: List of CIDR blocks to allow SSH from
            description: Optional description for the security group
            
        Returns:
            The created security group
        """
        ConfigValidator.validate_resource_name(name)
        
        for cidr in allowed_ssh_cidrs:
            ConfigValidator.validate_cidr_block(cidr)
        
        security_group = ec2.SecurityGroup(
            self,
            f"{name}-bastion-security-group",
            vpc=vpc,
            description=description or f"Bastion security group for {name}",
            allow_all_outbound=True
        )
        
        # Allow SSH from specified CIDRs
        for cidr in allowed_ssh_cidrs:
            security_group.add_ingress_rule(
                peer=ec2.Peer.ipv4(cidr),
                connection=ec2.Port.tcp(22),
                description=f"Allow SSH from {cidr}"
            )
        
        return security_group
