import { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Brain, TrendingUp, Lightbulb, CheckCircle2, Sparkles, MessageSquare, Zap, Clock } from "lucide-react";

export interface ConsensusResult {
  score: number;
  confidence?: number; // Optional for backward compatibility, maps to semantic_alignment
  keyInsights: string[];
  keyAlignments?: string[];
  proArguments?: string[];
  conArguments?: string[];
  semanticAlignment?: number;
  agreementRatio?: number;
  convergenceScore?: number;
  resolutionRate?: number;
  sentiment: "positive" | "neutral" | "negative";
  processingTime?: number; // Optional
}

interface DebateSimulationProps {
  /** Duration in milliseconds for the simulation phase */
  duration?: number;
  /** Callback when simulation completes */
  onComplete?: (result: ConsensusResult) => void;
  /** Whether to auto-start the simulation */
  autoStart?: boolean;
  /** Custom result data (if provided, will be used instead of generating mock data) */
  result?: ConsensusResult;
  /** Estimated processing time in seconds (for display) */
  processingTime?: number;
  /** Optional debate ID for session persistence */
  debateId?: string;
}

export function DebateSimulation({
  duration = 4000,
  onComplete,
  autoStart = true,
  result: customResult,
  processingTime,
  debateId,
}: DebateSimulationProps) {
  const [isLoading, setIsLoading] = useState(autoStart);
  const [result, setResult] = useState<ConsensusResult | null>(customResult || null);
  const [progress, setProgress] = useState(0);
  // Use refs to track if loading has started and preserve state across re-renders
  const loadingStartedRef = useRef(false);
  const progressIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  // Create a unique key for this debate session based on props
  const sessionKey = debateId 
    ? `debate-loading-${debateId}` 
    : `debate-loading-${duration}-${processingTime}`;

  useEffect(() => {
    // If custom result is provided or autoStart is false, don't start loading
    if (!autoStart || customResult) {
      loadingStartedRef.current = false;
      // Clear session storage when we have a result
      if (customResult) {
        sessionStorage.removeItem(sessionKey);
      }
      return;
    }

    // Check if loading has already started in this session (survives remounts)
    const hasStarted = sessionStorage.getItem(sessionKey) === 'true';
    if (hasStarted) {
      loadingStartedRef.current = true;
      setIsLoading(true);
      // Restore progress from session storage if available
      const savedProgress = sessionStorage.getItem(`${sessionKey}-progress`);
      if (savedProgress) {
        const progressValue = parseFloat(savedProgress);
        if (!isNaN(progressValue)) {
          setProgress(progressValue);
        }
      }
      
      // Restart the progress interval if duration is 0 or negative
      if (duration <= 0) {
        progressIntervalRef.current = setInterval(() => {
          setProgress((prev) => {
            const next = prev >= 90 ? 90 : prev + (90 - prev) * 0.02;
            sessionStorage.setItem(`${sessionKey}-progress`, next.toString());
            return next;
          });
        }, 2000);
        return () => {
          if (progressIntervalRef.current) {
            clearInterval(progressIntervalRef.current);
            progressIntervalRef.current = null;
          }
        };
      }
      
      // If duration is positive, we shouldn't be restoring (it should have completed)
      // But if we are restoring, just continue with the interval
      progressIntervalRef.current = setInterval(() => {
        setProgress((prev) => {
          const next = Math.min(prev + 2, 100);
          sessionStorage.setItem(`${sessionKey}-progress`, next.toString());
          return next;
        });
      }, duration / 50);
      
      return () => {
        if (progressIntervalRef.current) {
          clearInterval(progressIntervalRef.current);
          progressIntervalRef.current = null;
        }
      };
    }

    // If loading has already started in this component instance, don't restart it
    if (loadingStartedRef.current) {
      return;
    }

    loadingStartedRef.current = true;
    sessionStorage.setItem(sessionKey, 'true');

    // If duration is 0 or negative, stay in loading state indefinitely
    // (waiting for external result via customResult prop)
    if (duration <= 0) {
      setIsLoading(true);
      // More realistic progress: slower increment, cap at 90%
      progressIntervalRef.current = setInterval(() => {
        setProgress((prev) => {
          // Slow exponential progress that approaches 90% asymptotically
          const next = prev >= 90 ? 90 : prev + (90 - prev) * 0.02;
          // Persist progress to session storage
          sessionStorage.setItem(`${sessionKey}-progress`, next.toString());
          return next;
        });
      }, 2000); // Update every 2 seconds
      return () => {
        if (progressIntervalRef.current) {
          clearInterval(progressIntervalRef.current);
          progressIntervalRef.current = null;
        }
      };
    }

    // Simulate progress for positive duration
    progressIntervalRef.current = setInterval(() => {
      setProgress((prev) => {
        const next = Math.min(prev + 2, 100);
        // Persist progress to session storage
        sessionStorage.setItem(`${sessionKey}-progress`, next.toString());
        return next;
      });
    }, duration / 50);

    // Complete simulation after duration
    timeoutRef.current = setTimeout(() => {
      setIsLoading(false);
      const generatedResult: ConsensusResult = {
        score: 87,
        confidence: 92,
        keyInsights: [
          "Strong alignment on core objectives",
          "Divergent perspectives on implementation timeline",
          "Consensus reached on resource allocation",
        ],
        sentiment: "positive" as const,
        processingTime: duration / 1000,
      };
      setResult(generatedResult);
      // Clear session storage when completed
      sessionStorage.removeItem(sessionKey);
      sessionStorage.removeItem(`${sessionKey}-progress`);
      onComplete?.(generatedResult);
    }, duration);

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
        progressIntervalRef.current = null;
      }
    };
  }, [duration, onComplete, autoStart, customResult, sessionKey]);

  // If custom result is provided, show it immediately
  useEffect(() => {
    if (customResult) {
      setIsLoading(false);
      setResult(customResult);
      // Reset loading started flag when we receive a result
      loadingStartedRef.current = false;
      // Clear session storage when we receive a result
      sessionStorage.removeItem(sessionKey);
      sessionStorage.removeItem(`${sessionKey}-progress`);
    }
  }, [customResult, sessionKey]);

  return (
    <div className="w-full overflow-visible">
      <AnimatePresence mode="wait">
        {isLoading ? (
          <motion.div
            key="loading"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="relative"
          >
            <Card className="border-border/50">
              <CardHeader className="pb-4">
                <div className="flex items-center gap-3">
                  <motion.div
                    animate={{
                      rotate: [0, 360],
                      scale: [1, 1.1, 1],
                    }}
                    transition={{
                      rotate: {
                        duration: 2,
                        repeat: Infinity,
                        ease: "linear",
                      },
                      scale: {
                        duration: 1.5,
                        repeat: Infinity,
                        ease: "easeInOut",
                      },
                    }}
                  >
                    <Sparkles className="h-6 w-6 text-foreground" />
                  </motion.div>
                  <div>
                    <CardTitle className="text-lg">Analyzing Your Ideas</CardTitle>
                    <CardDescription className="mt-1">
                      We're processing your ideas and finding patterns...
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {/* Casual Loading Animation */}
                <div className="flex flex-col items-center justify-center py-12">
                  {/* Animated Icons */}
                  <div className="relative flex items-center justify-center gap-6 mb-8">
                    {[
                      { icon: MessageSquare, delay: 0 },
                      { icon: Sparkles, delay: 0.2 },
                      { icon: Zap, delay: 0.4 },
                    ].map(({ icon: Icon, delay }, index) => (
                      <motion.div
                        key={index}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{
                          opacity: [0.4, 1, 0.4],
                          y: [0, -10, 0],
                        }}
                        transition={{
                          duration: 1.5,
                          repeat: Infinity,
                          delay: delay,
                          ease: "easeInOut",
                        }}
                        className="p-4 rounded-full bg-muted"
                      >
                        <Icon className="h-8 w-8 text-foreground" />
                      </motion.div>
                    ))}
                  </div>

                  {/* Loading Dots */}
                  <div className="flex gap-2 mb-6">
                    {[0, 1, 2].map((index) => (
                      <motion.div
                        key={index}
                        className="h-3 w-3 rounded-full bg-foreground"
                        animate={{
                          scale: [1, 1.3, 1],
                          opacity: [0.5, 1, 0.5],
                        }}
                        transition={{
                          duration: 1,
                          repeat: Infinity,
                          delay: index * 0.2,
                          ease: "easeInOut",
                        }}
                      />
                    ))}
                  </div>

                  {/* Progress Bar */}
                  <div className="w-full max-w-md">
                    <div className="mb-2 flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">
                        {progress < 30 ? "Creating AI agents..." : 
                         progress < 60 ? "Simulating debate..." : 
                         progress < 90 ? "Analyzing consensus..." : 
                         "Finalizing results..."}
                      </span>
                      <span className="font-medium text-foreground">{Math.round(progress)}%</span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
                      <motion.div
                        className="h-full bg-foreground"
                        initial={{ width: "0%" }}
                        animate={{ width: `${progress}%` }}
                        transition={{ duration: 0.3, ease: "easeOut" }}
                      />
                    </div>
                  </div>

                  {/* Status Messages */}
                  <div className="mt-6 flex flex-wrap justify-center gap-2">
                    {[
                      "Creating AI agents",
                      "Running debate simulation",
                      "Analyzing consensus",
                    ].map((msg, i) => (
                      <motion.div
                        key={msg}
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{
                          opacity: progress > (i + 1) * 25 ? 1 : 0.4,
                          scale: progress > (i + 1) * 25 ? 1 : 0.9,
                        }}
                        transition={{ duration: 0.3 }}
                      >
                        <Badge variant="secondary" className="text-xs">
                          {msg}
                        </Badge>
                      </motion.div>
                    ))}
                  </div>
                  
                  {/* Time estimate */}
                  {progress < 90 && processingTime !== undefined && (
                    <motion.div
                      initial={{ opacity: 0, y: 5 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.3, duration: 0.4 }}
                      className="mt-6 flex items-center justify-center gap-2"
                    >
                      <motion.div
                        animate={{
                          scale: [1, 1.05, 1],
                        }}
                        transition={{
                          duration: 2,
                          repeat: Infinity,
                          ease: "easeInOut",
                        }}
                      >
                        <Clock className="h-3.5 w-3.5 text-muted-foreground/70" />
                      </motion.div>
                      <span className="text-xs text-muted-foreground/80 font-medium">
                        {processingTime < 120 ? (
                          <>~{Math.round(processingTime)} seconds</>
                        ) : (
                          <>~{Math.ceil(processingTime / 60)} minute{Math.ceil(processingTime / 60) > 1 ? 's' : ''}</>
                        )}
                      </span>
                    </motion.div>
                  )}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ) : result ? (
          <motion.div
            key="result"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.5 }}
          >
            <Card className="border-border/50">
              <CardHeader>
                <div className="flex items-center gap-3">
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: "spring", stiffness: 200, damping: 15 }}
                  >
                    <CheckCircle2 className="h-6 w-6 text-muted-foreground" />
                  </motion.div>
                  <div>
                    <CardTitle className="text-lg">Consensus Reached</CardTitle>
                    <CardDescription className="mt-1">
                      AI agents have synthesized collective intelligence
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-6 !pb-8">
                {/* Metrics Grid */}
                <div className="grid gap-4 md:grid-cols-3">
                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.1 }}
                  >
                    <Card className="border-border/50">
                      <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm font-medium text-muted-foreground">
                              Consensus Score
                            </p>
                            <p className="mt-2 text-3xl font-bold text-foreground">
                              {result.score}
                            </p>
                            <p className="text-xs text-muted-foreground">/ 100</p>
                          </div>
                          <TrendingUp className="h-10 w-10 text-muted-foreground" />
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>

                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.2 }}
                  >
                    <Card className="border-border/50">
                      <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm font-medium text-muted-foreground">
                              {result.semanticAlignment !== undefined ? "Alignment" : "Confidence"}
                            </p>
                            <p className="mt-2 text-3xl font-bold text-foreground">
                              {result.confidence !== undefined 
                                ? `${Math.round(result.confidence)}%`
                                : result.semanticAlignment !== undefined
                                ? `${Math.round(result.semanticAlignment)}%`
                                : "N/A"}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {result.semanticAlignment !== undefined ? "Semantic alignment" : "High reliability"}
                            </p>
                          </div>
                          <Brain className="h-10 w-10 text-muted-foreground" />
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>

                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.3 }}
                  >
                    <Card className="border-border/50">
                      <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm font-medium text-muted-foreground">Sentiment</p>
                            <p className="mt-2 text-3xl font-bold capitalize text-foreground">
                              {result.sentiment}
                            </p>
                            <p className="text-xs text-muted-foreground">Overall tone</p>
                          </div>
                          <Lightbulb className="h-10 w-10 text-muted-foreground" />
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                </div>

                {/* Key Insights */}
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.4 }}
                >
                  <Card className="border-border/50">
                    <CardHeader>
                      <CardTitle className="text-base flex items-center gap-2">
                        <Lightbulb className="h-4 w-4 text-muted-foreground" />
                        Key Insights
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ul className="space-y-3">
                        {result.keyInsights.map((insight, index) => (
                          <motion.li
                            key={index}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: 0.5 + index * 0.1 }}
                            className="flex items-start gap-3 text-sm text-foreground"
                          >
                            <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-muted-foreground" />
                            <span>{insight}</span>
                          </motion.li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                </motion.div>

                {/* Pro Arguments */}
                {result.proArguments && result.proArguments.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.5 }}
                  >
                    <Card className="border-border/50 transition-shadow duration-300 hover:shadow-[0_0_24px_rgba(34,197,94,0.25)]">
                      <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                          <TrendingUp className="h-4 w-4 text-muted-foreground" />
                          Pro Arguments
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ul className="space-y-3">
                          {result.proArguments.map((argument, index) => (
                            <motion.li
                              key={index}
                              initial={{ opacity: 0, x: -10 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ delay: 0.6 + index * 0.1 }}
                              className="flex items-start gap-3 text-sm text-foreground"
                            >
                              <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-green-500" />
                              <span>{argument}</span>
                            </motion.li>
                          ))}
                        </ul>
                      </CardContent>
                    </Card>
                  </motion.div>
                )}

                {/* Con Arguments */}
                {result.conArguments && result.conArguments.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.6 }}
                  >
                    <Card className="border-border/50 transition-shadow duration-300 hover:shadow-[0_0_24px_rgba(239,68,68,0.25)]">
                      <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                          <MessageSquare className="h-4 w-4 text-muted-foreground" />
                          Con Arguments
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ul className="space-y-3">
                          {result.conArguments.map((argument, index) => (
                            <motion.li
                              key={index}
                              initial={{ opacity: 0, x: -10 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ delay: 0.7 + index * 0.1 }}
                              className="flex items-start gap-3 text-sm text-foreground"
                            >
                              <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-red-500" />
                              <span>{argument}</span>
                            </motion.li>
                          ))}
                        </ul>
                      </CardContent>
                    </Card>
                  </motion.div>
                )}
              </CardContent>
            </Card>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

