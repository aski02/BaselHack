"""Debate orchestration service using CrewAI for agent creation and OpenAI for execution"""

import os
import logging
import traceback
from typing import List, Dict, Any, Optional
from crewai import Agent
from langchain_openai import ChatOpenAI
from app.core import config
from app.services.debate_storage import (
    create_debate, update_debate_status, add_debate_agent, add_debate_message,
    add_intervention, get_debate_messages
)
from openai import OpenAI

# Set up logging
logger = logging.getLogger(__name__)


# Set OpenAI API key for CrewAI
if config.OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = config.OPENAI_API_KEY


def get_openai_llm() -> ChatOpenAI:
    """
    Get OpenAI LLM instance for CrewAI
    
    Returns:
        ChatOpenAI instance configured with settings from config
        
    Raises:
        ValueError: If OPENAI_API_KEY is not set
    """
    if not config.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set in environment")
    
    return ChatOpenAI(
        model=config.OPENAI_MODEL,
        temperature=config.OPENAI_TEMPERATURE,
        max_tokens=config.OPENAI_MAX_TOKENS,
    )


def generate_agent_persona(cluster_submissions: List[str]) -> Dict[str, str]:
    """
    Generate agent persona (role, goal, backstory) from cluster submissions
    
    Args:
        cluster_submissions: List of submission texts in the cluster
    
    Returns:
        Dictionary with role, goal, and backstory
    """
    if not config.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set. Please set the OPENAI_API_KEY environment variable.")
    
    if not cluster_submissions:
        raise ValueError("Cannot generate persona from empty cluster submissions")
    
    try:
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        
        # Create a summary of cluster submissions
        submissions_to_use = cluster_submissions[:config.MAX_SUBMISSIONS_FOR_PERSONA]
        cluster_summary = "\n".join([f"- {sub}" for sub in submissions_to_use])
        
        prompt = f"""Based on the following opinions and ideas, create a coherent persona for a debate agent:

Opinions/Ideas:
{cluster_summary}

Create a persona with:
1. Role: A specific role/title (e.g., "Urban Sustainability Advocate", "Community Development Expert")
2. Goal: What this agent wants to achieve in the debate (one sentence)
3. Backstory: A brief 2-3 sentence backstory that explains why this agent holds these views

Respond in the following JSON format:
{{
    "role": "...",
    "goal": "...",
    "backstory": "..."
}}"""

        logger.info(f"Generating persona for cluster with {len(cluster_submissions)} submissions")
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=config.PERSONA_GENERATION_TEMPERATURE,
            response_format={"type": "json_object"}
        )
        
        import json
        response_content = response.choices[0].message.content
        if not response_content:
            raise ValueError("Empty response from OpenAI when generating persona")
        persona = json.loads(response_content)
        
        # Validate persona structure
        required_keys = ["role", "goal", "backstory"]
        for key in required_keys:
            if key not in persona:
                raise ValueError(f"Persona missing required key: {key}")
        
        logger.info(f"Generated persona: {persona['role']}")
        return persona
        
    except Exception as e:
        logger.error(f"Failed to generate agent persona: {str(e)}")
        logger.debug(traceback.format_exc())  # Use debug level for stack traces
        raise


def create_agents_from_clusters(
    clusters: List[List[str]],
    debate_id: str
) -> List[Agent]:
    """
    Create CrewAI agents from clusters
    
    Args:
        clusters: List of clusters, each containing submission texts
        debate_id: Debate identifier for storage
    
    Returns:
        List of CrewAI Agent objects
    """
    if not clusters:
        raise ValueError("Cannot create agents from empty clusters list")
    
    if not config.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set. Please set the OPENAI_API_KEY environment variable.")
    
    agents = []
    
    logger.info(f"Creating agents from {len(clusters)} clusters")
    
    for cluster_idx, cluster_submissions in enumerate(clusters):
        try:
            if not cluster_submissions:
                logger.warning(f"Skipping empty cluster {cluster_idx}")
                continue
            
            # Generate persona from cluster
            logger.info(f"Processing cluster {cluster_idx} with {len(cluster_submissions)} submissions")
            persona = generate_agent_persona(cluster_submissions)
            
            # Create agent
            agent = Agent(
                role=persona["role"],
                goal=persona["goal"],
                backstory=persona["backstory"],
                llm=get_openai_llm(),
                verbose=True,
                allow_delegation=False,
            )
            
            agents.append(agent)
            
            # Store agent in database
            agent_id = f"agent_{cluster_idx}"
            agent_name = persona["role"]
            add_debate_agent(debate_id, agent_id, agent_name, cluster_idx, persona["backstory"])
            logger.info(f"Created agent {agent_id}: {agent_name}")
            
        except Exception as e:
            logger.error(f"Failed to create agent for cluster {cluster_idx}: {str(e)}")
            logger.error(traceback.format_exc())
            # Continue with other clusters rather than failing completely
            continue
    
    if not agents:
        raise ValueError(f"No agents created from {len(clusters)} clusters. Check logs for details.")
    
    logger.info(f"Successfully created {len(agents)} agents")
    return agents


def check_for_intervention(
    messages: List[Dict[str, Any]],
    round_number: int,
    max_rounds: int,
    max_messages: int
) -> Optional[Dict[str, Any]]:
    """
    Check if orchestrator should intervene based on debate state
    
    Args:
        messages: List of all debate messages
        round_number: Current round number
        max_rounds: Maximum allowed rounds
        max_messages: Maximum allowed messages
    
    Returns:
        None if no intervention needed, or dict with:
        - intervention_type: Type of intervention (max_rounds, max_messages, repetition, off_topic, stalemate, ethical)
        - reason: Reason for intervention
        - message: Intervention message to display
    """
    from app.services.clustering import get_model
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    
    # Check max rounds
    if round_number >= max_rounds:
        return {
            "intervention_type": "max_rounds",
            "reason": f"Maximum rounds ({max_rounds}) reached",
            "message": "The debate has reached the maximum number of rounds. Let's summarize the key points discussed."
        }
    
    # Check max messages
    if len(messages) >= max_messages:
        return {
            "intervention_type": "max_messages",
            "reason": f"Maximum messages ({max_messages}) reached",
            "message": "The debate has reached the maximum number of messages. Let's wrap up with a summary."
        }
    
    if len(messages) < config.MIN_MESSAGES_FOR_INTERVENTION:
        return None
    
    # Check for repetition (last 3-5 messages are similar)
    recent_messages = messages[-5:] if len(messages) >= 5 else messages
    
    if len(recent_messages) >= config.MIN_MESSAGES_FOR_INTERVENTION:
        # Embed recent messages
        model = get_model()
        contents = [msg["content"] for msg in recent_messages]
        embeddings = model.encode(contents, convert_to_numpy=True, normalize_embeddings=True)
        
        # Check pairwise similarities
        similarities = cosine_similarity(embeddings)
        avg_similarity = np.mean([similarities[i][j] for i in range(len(similarities)) for j in range(i+1, len(similarities))])
        
        if avg_similarity > config.REPETITION_SIMILARITY_THRESHOLD:
            return {
                "intervention_type": "repetition",
                "reason": "Similar points are being repeated",
                "message": "I notice similar points are being repeated. Let's move forward and explore new aspects of the topic or address different perspectives."
            }
    
    # Check for off-topic (compare with first few messages)
    if len(messages) >= 6:
        early_messages = messages[:3]
        recent_messages = messages[-3:]
        
        early_content = " ".join([msg["content"] for msg in early_messages])
        recent_content = " ".join([msg["content"] for msg in recent_messages])
        
        model = get_model()
        embeddings = model.encode([early_content, recent_content], convert_to_numpy=True, normalize_embeddings=True)
        similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
        
        if similarity < config.INTERVENTION_OFF_TOPIC_THRESHOLD:
            return {
                "intervention_type": "off_topic",
                "reason": "Discussion has drifted off-topic",
                "message": "The discussion seems to have drifted from the original topic. Let's refocus on the core issues at hand."
            }
    
    # Check for stalemate (same arguments repeated across rounds)
    if round_number >= config.INTERVENTION_STALEMATE_THRESHOLD:
        # Check if agents are stuck on same points
        rounds_to_check = min(round_number, config.MIN_ROUNDS_FOR_STALEMATE_CHECK)
        rounds_checked = []
        for r in range(max(1, round_number - rounds_to_check + 1), round_number + 1):
            round_messages = [msg for msg in messages if msg["round_number"] == r]
            if round_messages:
                rounds_checked.append(" ".join([msg["content"] for msg in round_messages]))
        
        if len(rounds_checked) >= config.MIN_MESSAGES_FOR_INTERVENTION:
            model = get_model()
            embeddings = model.encode(rounds_checked, convert_to_numpy=True, normalize_embeddings=True)
            similarities = cosine_similarity(embeddings)
            avg_sim = np.mean([similarities[i][j] for i in range(len(similarities)) for j in range(i+1, len(similarities))])
            
            if avg_sim > config.STALEMATE_SIMILARITY_THRESHOLD:
                return {
                    "intervention_type": "stalemate",
                    "reason": "Debate appears stalled with repeated arguments",
                    "message": "It seems we're circling the same arguments. Let's try to synthesize the key points and identify areas of potential agreement or new angles to explore."
                }
    
    # Check for ethical violations (insults, profanity)
    if config.DETECT_ETHICAL_VIOLATIONS:
        insult_keywords = ["stupid", "idiot", "fool", "moron", "ridiculous", "nonsense"]
        last_message = messages[-1]["content"].lower()
        
        if any(keyword in last_message for keyword in insult_keywords):
            return {
                "intervention_type": "ethical",
                "reason": "Detected inappropriate language",
                "message": "Let's maintain a respectful tone. Please express disagreements constructively without personal attacks or inappropriate language."
            }
    
    return None


def run_debate(
    project_id: str,
    debate_id: str,
    max_rounds: int = None,
    max_messages: int = None
) -> Dict[str, Any]:
    """
    Run a debate simulation using OpenAI chat completions with message tracking
    
    Args:
        project_id: Project identifier
        debate_id: Debate identifier
        max_rounds: Maximum number of rounds (default from config)
        max_messages: Maximum number of messages (default from config)
    
    Returns:
        Dictionary with debate results
    """
    if max_rounds is None:
        max_rounds = config.DEFAULT_MAX_ROUNDS
    if max_messages is None:
        max_messages = config.DEFAULT_MAX_MESSAGES
    
    try:
        logger.info(f"Starting debate {debate_id} for project {project_id}")
        update_debate_status(debate_id, "running")
        
        # Get clusters for the project
        import numpy as np
        
        # Get submissions and cluster them
        from app.services.database import get_submissions
        logger.info(f"Retrieving submissions for project {project_id}")
        results = get_submissions(project_id)
        if not results["ids"]:
            raise ValueError(f"No submissions found for project {project_id}")
        
        logger.info(f"Found {len(results['ids'])} submissions")
        submissions = results["documents"]
        embeddings = np.array(results["embeddings"])
        
        from app.services.clustering import cluster_submissions
        logger.info("Clustering submissions...")
        clusters, num_clusters, _ = cluster_submissions(submissions, embeddings)
        logger.info(f"Created {num_clusters} clusters from submissions")
        
        if not clusters or len(clusters) == 0:
            raise ValueError(f"No clusters created from submissions. This may indicate all submissions are too similar.")
        
        # Create agents from clusters
        logger.info(f"Creating agents from {len(clusters)} clusters...")
        agents = create_agents_from_clusters(clusters, debate_id)
        
        if not agents:
            raise ValueError(f"No agents created from {len(clusters)} clusters. Check logs for details.")
        
        logger.info(f"Successfully created {len(agents)} agents")
        
        # Create orchestrator (store but use OpenAI directly)
        add_debate_agent(debate_id, "orchestrator", "Debate Moderator", -1, "Facilitates productive debate")
        
        # Build agent personas for OpenAI chat
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        
        # Build system messages for each agent
        agent_system_messages = {}
        for i, agent in enumerate(agents):
            agent_id = f"agent_{i}"
            agent_system_messages[agent_id] = f"""You are {agent.role}. Your goal: {agent.goal}. 

Background: {agent.backstory}

You are participating in a structured debate. Guidelines:
- Present your perspective clearly and concisely
- Listen to and respond to other agents' viewpoints
- Look for areas of agreement and potential synthesis
- Stay on topic and avoid repetition
- Maintain respectful and constructive discourse
- Keep responses under {config.AGENT_MESSAGE_MAX_WORDS} words"""

        orchestrator_system = """You are a Debate Moderator. Your role is to facilitate productive debate by maintaining focus, preventing repetition, detecting stalemates, and ensuring respectful discourse. 

Intervene when:
- The debate becomes repetitive
- Discussion goes off-topic
- A stalemate is reached
- Ethical violations occur (insults, profanity)
- Maximum rounds/messages are reached

Keep interventions brief and constructive."""
        
        # Initialize debate
        debate_history = []  # For OpenAI chat format
        round_number = 1
        message_count = 0
        current_agent_idx = 0
        
        # Add opening message from orchestrator
        opening = f"Welcome to the debate. We have {len(agents)} perspectives to explore. Let's begin with {agents[0].role}."
        add_debate_message(debate_id, "orchestrator", "Debate Moderator", opening, round_number, "orchestrator_message")
        debate_history.append({"role": "assistant", "content": opening})
        message_count += 1
        
        # Run debate rounds
        while round_number <= max_rounds and message_count < max_messages:
            # Current agent speaks
            agent_id = f"agent_{current_agent_idx}"
            agent = agents[current_agent_idx]
            
            # Build conversation history for this agent
            # Include system message and recent history
            conversation = [
                {"role": "system", "content": agent_system_messages[agent_id]},
            ] + debate_history[-config.DEBATE_CONTEXT_MESSAGE_LIMIT:]
            
            # Get agent response
            agent_max_tokens = int(config.OPENAI_MAX_TOKENS * config.AGENT_MESSAGE_MAX_TOKENS_RATIO)
            response = client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=conversation,
                temperature=config.OPENAI_TEMPERATURE,
                max_tokens=agent_max_tokens,
            )
            
            agent_message = response.choices[0].message.content
            if not agent_message:
                logger.warning(f"Empty response from agent {agent_id} in round {round_number}, skipping")
                current_agent_idx = (current_agent_idx + 1) % len(agents)
                if current_agent_idx == 0:
                    round_number += 1
                continue
            
            add_debate_message(debate_id, agent_id, agent.role, agent_message, round_number, "agent_message")
            debate_history.append({"role": "user", "content": f"{agent.role}: {agent_message}"})
            message_count += 1
            
            # Check for intervention
            stored_messages = get_debate_messages(debate_id)["messages"]
            intervention = check_for_intervention(stored_messages, round_number, max_rounds, max_messages)
            
            if intervention:
                intervention_msg = intervention.get("message", intervention["reason"])
                add_intervention(debate_id, intervention["intervention_type"], intervention["reason"], intervention_msg)
                add_debate_message(debate_id, "orchestrator", "Debate Moderator", intervention_msg, round_number, "orchestrator_message")
                debate_history.append({"role": "assistant", "content": f"Moderator: {intervention_msg}"})
                message_count += 1
                
                # If max rounds/messages reached, end debate
                if intervention["intervention_type"] in ["max_rounds", "max_messages"]:
                    break
            
            # Move to next agent (round-robin)
            current_agent_idx = (current_agent_idx + 1) % len(agents)
            
            # New round after all agents have spoken
            if current_agent_idx == 0:
                round_number += 1
        
        # Final summary from orchestrator
        final_msg = f"The debate has concluded after {round_number} rounds with {message_count} messages. Thank you all for your contributions."
        add_debate_message(debate_id, "orchestrator", "Debate Moderator", final_msg, round_number, "orchestrator_message")
        
        # Calculate consensus and generate summary
        from app.services.consensus_analysis import calculate_consensus_score
        from app.services.debate_storage import store_consensus_analysis, store_debate_summary
        
        consensus_data = calculate_consensus_score(debate_id)
        store_consensus_analysis(
            debate_id,
            consensus_data["consensus_score"],
            consensus_data["semantic_alignment"] / 100.0,  # Convert back to 0-1
            consensus_data["agreement_ratio"] / 100.0,
            consensus_data["convergence_score"] / 100.0,
            consensus_data["resolution_rate"] / 100.0,
            consensus_data["sentiment"]
        )
        
        summary = generate_debate_summary(debate_id)
        store_debate_summary(
            debate_id,
            summary["key_alignments"],
            summary["key_insights"],
            summary["pro_arguments"],
            summary["con_arguments"]
        )
        
        update_debate_status(debate_id, "completed", consensus_data["consensus_score"])
        
        return {
            "debate_id": debate_id,
            "status": "completed",
            "rounds": round_number,
            "messages": message_count,
            "consensus_score": consensus_data["consensus_score"],
        }
        
    except Exception as e:
        error_message = f"Debate execution failed: {str(e)}"
        error_traceback = traceback.format_exc()
        logger.error(error_message)
        logger.error(error_traceback)
        
        # Update status with error message
        try:
            update_debate_status(debate_id, "cancelled", error_message=error_message)
        except Exception as update_error:
            logger.error(f"Failed to update debate status: {str(update_error)}")
        
        raise


def generate_debate_summary(debate_id: str) -> Dict[str, Any]:
    """
    Generate summary of debate including key alignments, insights, and arguments
    
    Args:
        debate_id: Debate identifier
    
    Returns:
        Dictionary with summary data
    """
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    
    # Get all messages
    messages_data = get_debate_messages(debate_id)
    messages = messages_data["messages"]
    
    if not messages:
        return {
            "key_alignments": [],
            "key_insights": [],
            "pro_arguments": [],
            "con_arguments": [],
        }
    
    # Build transcript
    transcript = "\n\n".join([
        f"[{msg['agent_name']}]: {msg['content']}"
        for msg in messages
    ])
    
    prompt = f"""Analyze the following debate transcript and extract:

1. Key Alignments: Common ground, agreed-upon principles, shared values (3-5 items)
2. Key Insights: Important conclusions, novel perspectives, important takeaways (3-5 items)
3. Pro Arguments: Strongest supporting arguments for the main topic, ranked by strength (3-5 items)
4. Con Arguments: Strongest opposing or alternative arguments, ranked by strength (3-5 items)

Debate Transcript:
{transcript}

Respond in JSON format:
{{
    "key_alignments": ["...", "..."],
    "key_insights": ["...", "..."],
    "pro_arguments": ["...", "..."],
    "con_arguments": ["...", "..."]
}}"""

    response = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=config.PERSONA_GENERATION_TEMPERATURE,
        response_format={"type": "json_object"}
    )
    
    import json
    response_content = response.choices[0].message.content
    if not response_content:
        logger.warning(f"Empty summary response for debate {debate_id}, returning defaults")
        return {
            "key_alignments": [],
            "key_insights": [],
            "pro_arguments": [],
            "con_arguments": [],
        }
    
    try:
        summary = json.loads(response_content)
        # Validate summary structure
        required_keys = ["key_alignments", "key_insights", "pro_arguments", "con_arguments"]
        for key in required_keys:
            if key not in summary:
                summary[key] = []
        return summary
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse debate summary JSON: {str(e)}")
        return {
            "key_alignments": [],
            "key_insights": [],
            "pro_arguments": [],
            "con_arguments": [],
        }

