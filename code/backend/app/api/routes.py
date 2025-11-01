"""API routes for submission clustering"""

import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.schemas import (
    StoreSubmissionsRequest, StoreSubmissionsResponse, ClusterResponse,
    CreateDebateRequest, CreateDebateResponse, DebateListResponse, DebateResponse,
    ConsensusResponse, MessageResponse, AgentInfo, InterventionResponse
)
from app.services.clustering import cluster_submissions
from app.services.database import add_submissions, get_submissions
from app.services.debate import run_debate
from app.services.debate_storage import (
    create_debate, get_debate, list_debates, get_debate_agents,
    get_debate_messages, get_debate_interventions,
    get_consensus_analysis, get_debate_summary
)
from app.services.consensus_analysis import calculate_consensus_score, calculate_pairwise_alignment_matrix
from app.core import config
import numpy as np

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@router.post("/projects/{project_id}/submissions", response_model=StoreSubmissionsResponse)
async def store_submissions_endpoint(project_id: str, request: StoreSubmissionsRequest):
    """
    Store submissions for a project in the vector database with embeddings.
    Automatically computes embeddings for each submission.
    """
    try:
        ids = add_submissions(request.submissions, project_id)
        return StoreSubmissionsResponse(
            ids=ids,
            message="Submissions stored successfully",
            count=len(ids)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store submissions: {str(e)}")


@router.get("/projects/{project_id}/clusters", response_model=ClusterResponse)
async def get_clusters(project_id: str):
    """
    Get clusters for a project by semantic similarity.
    Retrieves stored submissions from the database and performs clustering analysis.
    """
    try:
        # Retrieve submissions from database
        results = get_submissions(project_id)
        
        if not results["ids"] or len(results["ids"]) < config.MIN_SUBMISSIONS_FOR_CLUSTERING:
            raise HTTPException(
                status_code=400, 
                detail=f"Need at least {config.MIN_SUBMISSIONS_FOR_CLUSTERING} stored submissions for project '{project_id}'. Found: {len(results.get('ids', []))}"
            )
        
        submissions = results["documents"]
        embeddings = np.array(results["embeddings"])
        
        # Cluster using stored embeddings
        clusters, num_clusters, silhouette = cluster_submissions(submissions, embeddings)
        
        return ClusterResponse(
            clusters=clusters,
            num_clusters=num_clusters,
            silhouette_score=silhouette
        )
            
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clustering failed: {str(e)}")


@router.post("/projects/{project_id}/debates", response_model=CreateDebateResponse)
async def create_debate_endpoint(
    project_id: str,
    request: CreateDebateRequest,
    background_tasks: BackgroundTasks
):
    """
    Start a new debate from clusters for a project.
    Debate runs asynchronously in the background.
    """
    try:
        # Verify project has submissions
        results = get_submissions(project_id)
        if not results["ids"]:
            raise HTTPException(
                status_code=400,
                detail=f"No submissions found for project '{project_id}'"
            )
        
        # Create debate
        debate_id = create_debate(project_id, status="pending")
        
        # Start debate in background with error handling
        def run_debate_with_logging(*args, **kwargs):
            """Wrapper to log errors from background task"""
            try:
                return run_debate(*args, **kwargs)
            except Exception as e:
                logger.error(f"Background task error for debate {kwargs.get('debate_id', 'unknown')}: {str(e)}", exc_info=True)
                raise
        
        background_tasks.add_task(
            run_debate_with_logging,
            project_id=project_id,
            debate_id=debate_id,
            max_rounds=request.max_rounds,
            max_messages=request.max_messages
        )
        
        logger.info(f"Started debate {debate_id} for project {project_id}")
        
        # Get agents (will be created during debate execution)
        agents = get_debate_agents(debate_id)
        
        debate = get_debate(debate_id)
        
        return CreateDebateResponse(
            debate_id=debate_id,
            status=debate["status"],
            agents=[AgentInfo(**agent) for agent in agents],
            created_at=debate["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create debate: {str(e)}")


@router.get("/projects/{project_id}/debates", response_model=DebateListResponse)
async def list_debates_endpoint(project_id: str):
    """List all debates for a project"""
    try:
        debates = list_debates(project_id)
        return DebateListResponse(debates=debates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list debates: {str(e)}")


@router.get("/debates/{debate_id}", response_model=DebateResponse)
async def get_debate_endpoint(debate_id: str):
    """Get debate details and full conversation"""
    try:
        debate = get_debate(debate_id)
        if not debate:
            raise HTTPException(status_code=404, detail=f"Debate '{debate_id}' not found")
        
        agents = get_debate_agents(debate_id)
        messages_data = get_debate_messages(debate_id)
        interventions = get_debate_interventions(debate_id)
        
        return DebateResponse(
            debate_id=debate_id,
            project_id=debate["project_id"],
            status=debate["status"],
            consensus_score=debate.get("consensus_score"),
            error_message=debate.get("error_message"),
            agents=[AgentInfo(**agent) for agent in agents],
            messages=[MessageResponse(**msg) for msg in messages_data["messages"]],
            interventions=[InterventionResponse(**intervention) for intervention in interventions],
            created_at=debate["created_at"],
            updated_at=debate["updated_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get debate: {str(e)}")


@router.get("/debates/{debate_id}/messages")
async def get_debate_messages_endpoint(
    debate_id: str,
    limit: int = 50,
    offset: int = 0,
    agent_id: str = None
):
    """Get paginated messages for a debate"""
    try:
        debate = get_debate(debate_id)
        if not debate:
            raise HTTPException(status_code=404, detail=f"Debate '{debate_id}' not found")
        
        messages_data = get_debate_messages(debate_id, limit=limit, offset=offset, agent_id=agent_id)
        
        return {
            "messages": [MessageResponse(**msg) for msg in messages_data["messages"]],
            "total": messages_data["total"],
            "limit": messages_data["limit"],
            "offset": messages_data["offset"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get messages: {str(e)}")


@router.get("/debates/{debate_id}/consensus", response_model=ConsensusResponse)
async def get_consensus_endpoint(debate_id: str):
    """Get consensus analysis and summary for a debate"""
    try:
        debate = get_debate(debate_id)
        if not debate:
            raise HTTPException(status_code=404, detail=f"Debate '{debate_id}' not found")
        
        # Get consensus analysis
        consensus_analysis = get_consensus_analysis(debate_id)
        if not consensus_analysis:
            # Calculate if not already stored
            consensus_data = calculate_consensus_score(debate_id)
            from app.services.debate_storage import store_consensus_analysis
            store_consensus_analysis(
                debate_id,
                consensus_data["consensus_score"],
                consensus_data["semantic_alignment"] / 100,
                consensus_data["agreement_ratio"] / 100,
                consensus_data["convergence_score"] / 100,
                consensus_data["resolution_rate"] / 100,
                consensus_data["sentiment"]
            )
            consensus_analysis = get_consensus_analysis(debate_id)
        
        # Get summary
        summary = get_debate_summary(debate_id)
        if not summary:
            # Generate if not already stored
            from app.services.debate import generate_debate_summary
            from app.services.debate_storage import store_debate_summary
            summary_data = generate_debate_summary(debate_id)
            store_debate_summary(
                debate_id,
                summary_data["key_alignments"],
                summary_data["key_insights"],
                summary_data["pro_arguments"],
                summary_data["con_arguments"]
            )
            summary = get_debate_summary(debate_id)
        
        # Get pairwise alignment
        alignment_matrix = calculate_pairwise_alignment_matrix(debate_id)
        
        return ConsensusResponse(
            consensus_score=consensus_analysis["consensus_score"],
            semantic_alignment=consensus_analysis["semantic_alignment"] * 100,
            agreement_ratio=consensus_analysis["agreement_ratio"] * 100,
            convergence_score=consensus_analysis["convergence_score"] * 100,
            resolution_rate=consensus_analysis["resolution_rate"] * 100,
            sentiment=consensus_analysis["sentiment"],
            key_alignments=summary["key_alignments"],
            key_insights=summary["key_insights"],
            pro_arguments=summary["pro_arguments"],
            con_arguments=summary["con_arguments"],
            pairwise_alignment=alignment_matrix
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get consensus: {str(e)}")
