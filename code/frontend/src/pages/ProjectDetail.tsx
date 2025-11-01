import { useState, useRef, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowLeft, Sparkles, BarChart3, Network, Users } from "lucide-react";
import { DebateSimulation } from "@/components/DebateSimulation";
import type { ConsensusResult } from "@/components/DebateSimulation";
import { createMockDebate, getDebateStatus, getConsensusResults, estimateDebateDuration } from "@/lib/api";
import { toast } from "sonner";

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<ConsensusResult | null>(null);
  const [debateId, setDebateId] = useState<string | null>(null);
  const [estimatedTime, setEstimatedTime] = useState<number>(0);
  const [activeTab, setActiveTab] = useState("clusters");
  const loadingSectionRef = useRef<HTMLDivElement>(null);
  const synthesizeSectionRef = useRef<HTMLDivElement>(null);

  // Mock data - in real app would fetch based on id
  const projectsData: Record<string, {
    id: string;
    title: string;
    goal: string;
    status: string;
    ideasCount: number;
    lastActivity: string;
  }> = {
    "1": {
      id: "1",
      title: "Green City Basel",
      goal: "Collecting the best ideas for making Basel more sustainable",
      status: "collecting",
      ideasCount: 23,
      lastActivity: "2 hours ago",
    },
    "2": {
      id: "2",
      title: "Team-Building Adventure",
      goal: "Ideation on the best team-building activities for the next quarter.",
      status: "synthesizing",
      ideasCount: 45,
      lastActivity: "1 day ago",
    },
    "3": {
      id: "3",
      title: "From Chemical Plants to Food Production",
      goal: "Ideating on how to bring together industry professionals from diverse backgrounds?",
      status: "synthesizing",
      ideasCount: 23,
      lastActivity: "3 days ago",
    },
  };

  const project = projectsData[id || "1"] || projectsData["1"];

  // Handler for starting analysis
  const handleStartAnalysis = async () => {
    if (analysisResult) {
      // Reset and start fresh
      setAnalysisResult(null);
    }
    
    setIsAnalyzing(true);
    setDebateId(null);
    
    try {
      const projectId = id || "1";
      
      // Calculate estimated duration dynamically
      const maxRounds = undefined; // Use backend defaults
      const maxMessages = undefined; // Use backend defaults
      const estimatedSeconds = estimateDebateDuration(maxRounds, maxMessages);
      const estimatedMinutes = Math.ceil(estimatedSeconds / 60);
      
      const response = await createMockDebate(projectId, maxRounds, maxMessages);
      setDebateId(response.debate_id);
      setEstimatedTime(estimatedSeconds);
      toast.success(`Debate simulation started - estimated time: ${estimatedMinutes} minute${estimatedMinutes > 1 ? 's' : ''}`);
      
      // Scroll to loading animation after a short delay to ensure it's rendered
      setTimeout(() => {
        loadingSectionRef.current?.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'start' 
        });
      }, 100);
    } catch (error) {
      console.error("Failed to start debate:", error);
      toast.error(`Failed to start debate: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setIsAnalyzing(false);
    }
  };

  // Poll for debate status
  useEffect(() => {
    if (!debateId || !isAnalyzing) return;

    const pollInterval = setInterval(async () => {
      try {
        const debate = await getDebateStatus(debateId);
        
        if (debate.status === "completed") {
          clearInterval(pollInterval);
          
          // Fetch consensus results
          try {
            const consensusData = await getConsensusResults(debateId);
            
            // Transform backend response to ConsensusResult format
            const result: ConsensusResult = {
              score: consensusData.consensus_score,
              confidence: consensusData.semantic_alignment, // Map semantic_alignment to confidence
              keyInsights: consensusData.key_insights,
              keyAlignments: consensusData.key_alignments,
              proArguments: consensusData.pro_arguments,
              conArguments: consensusData.con_arguments,
              semanticAlignment: consensusData.semantic_alignment,
              agreementRatio: consensusData.agreement_ratio,
              convergenceScore: consensusData.convergence_score,
              resolutionRate: consensusData.resolution_rate,
              sentiment: consensusData.sentiment as "positive" | "neutral" | "negative",
            };
            
            handleAnalysisComplete(result);
          } catch (error) {
            console.error("Failed to fetch consensus results:", error);
            toast.error(`Failed to fetch results: ${error instanceof Error ? error.message : 'Unknown error'}`);
            setIsAnalyzing(false);
          }
        } else if (debate.status === "cancelled" || debate.error_message) {
          clearInterval(pollInterval);
          toast.error(`Debate failed: ${debate.error_message || 'Unknown error'}`);
          setIsAnalyzing(false);
        }
      } catch (error) {
        console.error("Failed to poll debate status:", error);
        // Continue polling on error (might be transient)
      }
    }, 2500); // Poll every 2.5 seconds

    return () => clearInterval(pollInterval);
  }, [debateId, isAnalyzing]);

  // Handler for when analysis completes
  const handleAnalysisComplete = (result: ConsensusResult) => {
    setAnalysisResult(result);
    setIsAnalyzing(false);
    setDebateId(null);
    
    // Scroll to synthesize section to move the analysis UI to the top
    // Use a small delay to ensure the result is rendered
    setTimeout(() => {
      synthesizeSectionRef.current?.scrollIntoView({ 
        behavior: 'smooth', 
        block: 'start' 
      });
    }, 100);
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-card">
        <div className="container mx-auto px-6 py-6">
          <Button variant="ghost" onClick={() => navigate("/")} className="mb-4">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Dashboard
          </Button>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-foreground">{project.title}</h1>
              <p className="mt-1 text-muted-foreground">{project.goal}</p>
            </div>
            <Badge className="bg-accent text-accent-foreground">Active</Badge>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-6 py-8">
        <div className="mb-8 grid gap-6 md:grid-cols-4">
          <Card>
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-sm font-medium text-muted-foreground">Total Ideas</p>
                <p className="mt-2 text-4xl font-bold text-foreground">{project.ideasCount}</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-sm font-medium text-muted-foreground">Contributors</p>
                <p className="mt-2 text-4xl font-bold text-foreground">12</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-sm font-medium text-muted-foreground">Themes Identified</p>
                <p className="mt-2 text-4xl font-bold text-foreground">5</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-sm font-medium text-muted-foreground">Consensus Score</p>
                <p className="mt-2 text-4xl font-bold text-foreground">78%</p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Synthesize Section */}
        <div ref={synthesizeSectionRef} className="mt-8">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="clusters">
                <Network className="mr-2 h-4 w-4" />
                Cluster Info
              </TabsTrigger>
              <TabsTrigger value="debate">
                <Users className="mr-2 h-4 w-4" />
                Agent Debate
                {isAnalyzing && (
                  <motion.span
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="ml-2 h-2 w-2 rounded-full bg-primary"
                  />
                )}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="clusters">
              <Card>
                <CardHeader>
                  <CardTitle>Idea Clusters</CardTitle>
                  <CardDescription>Interactive visualization of collected ideas grouped by similarity</CardDescription>
                </CardHeader>
                <CardContent className="flex h-96 items-center justify-center bg-muted/30">
                  <div className="text-center">
                    <BarChart3 className="mx-auto h-16 w-16 text-muted-foreground" />
                    <p className="mt-4 text-muted-foreground">
                      Visualization will appear here once you run the analysis
                    </p>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="debate">
              {!isAnalyzing && !analysisResult ? (
                <Card>
                  <CardHeader>
                    <CardTitle>Synthesize</CardTitle>
                    <CardDescription>AI agents simulate debate to form consensus from your collected ideas</CardDescription>
                  </CardHeader>
                  <CardContent className="flex h-96 items-center justify-center bg-muted/30">
                    <div className="text-center">
                      <Sparkles className="mx-auto h-16 w-16 text-muted-foreground" />
                      <p className="mt-4 text-muted-foreground mb-6">
                        Start the simulated debate to synthesize insights
                      </p>
                      <Button
                        size="lg"
                        className="bg-primary hover:bg-primary/90"
                        onClick={handleStartAnalysis}
                      >
                        <Sparkles className="mr-2 h-5 w-5" />
                        Start Simulation
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ) : isAnalyzing && !analysisResult ? (
                <div ref={loadingSectionRef} className="w-full overflow-visible">
                  <DebateSimulation
                    key={debateId || "debate-loading"}
                    duration={0} // No auto-complete, wait for real results
                    autoStart={true}
                    onComplete={handleAnalysisComplete}
                    processingTime={estimatedTime}
                    debateId={debateId || undefined}
                  />
                </div>
              ) : analysisResult ? (
                <div className="w-full overflow-visible pb-4">
                  <DebateSimulation key="debate-result" result={analysisResult} autoStart={false} />
                </div>
              ) : null}
            </TabsContent>
          </Tabs>
        </div>
      </main>
    </div>
  );
}
