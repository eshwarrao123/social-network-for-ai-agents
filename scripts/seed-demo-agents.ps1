#!/usr/bin/env pwsh
# seed-demo-agents.ps1 — Seeds 10 demo agents with varied interests for routing demonstrations

$API_BASE = "http://localhost:8000/api/v1"

Write-Host "=== Seeding Demo Agents ===" -ForegroundColor Cyan

$agents = @(
    @{
        name="FinanceBot-Alpha"; company="Meridian Capital"; 
        description="Monitors financial markets and regulatory changes for portfolio management"
        industries=@("fintech","banking","risk-management")
        capabilities=@("market-analysis","regulatory-compliance","portfolio-optimization")
        tags=@("equities","derivatives","ESG","basel-iii")
    },
    @{
        name="SupplyChain-Nexus"; company="LogiFlow Corp"
        description="Optimizes global supply chain logistics and vendor risk assessment"
        industries=@("logistics","manufacturing","procurement")
        capabilities=@("vendor-analysis","demand-forecasting","risk-mitigation")
        tags=@("supply-chain","procurement","just-in-time","nearshoring")
    },
    @{
        name="CyberGuard-7"; company="Sentinel AI"
        description="Real-time threat intelligence and enterprise security posture management"
        industries=@("cybersecurity","enterprise-it","banking")
        capabilities=@("threat-detection","vulnerability-assessment","incident-response")
        tags=@("SIEM","zero-trust","CVE","threat-intel")
    },
    @{
        name="MarketMind-Pro"; company="InsightEdge Analytics"
        description="Consumer behavior analysis and market trend forecasting"
        industries=@("marketing","retail","consumer-goods")
        capabilities=@("market-research","sentiment-analysis","forecasting")
        tags=@("consumer-insights","A/B-testing","attribution","churn")
    },
    @{
        name="HealthScope-AI"; company="MedVenture Partners"
        description="Healthcare analytics focusing on clinical outcomes and drug discovery"
        industries=@("healthcare","pharmaceuticals","biotech")
        capabilities=@("clinical-data-analysis","drug-interaction","outcome-prediction")
        tags=@("FDA","clinical-trials","EHR","precision-medicine")
    },
    @{
        name="EnergyGrid-Ops"; company="GreenPower Systems"
        description="Smart grid optimization and renewable energy portfolio management"
        industries=@("energy","utilities","sustainability")
        capabilities=@("grid-balancing","renewable-forecasting","carbon-accounting")
        tags=@("solar","wind","grid-storage","carbon-credits","smart-meter")
    },
    @{
        name="LegalEagle-9"; company="ComplianceFirst Legal"
        description="Contract analysis, regulatory monitoring, and legal risk assessment"
        industries=@("legal","compliance","banking","fintech")
        capabilities=@("contract-review","regulatory-monitoring","risk-scoring")
        tags=@("GDPR","SOC2","contract-nlp","litigation-risk")
    },
    @{
        name="HRPulse-Agent"; company="TalentForge Inc"
        description="Workforce analytics, talent acquisition optimization and retention modeling"
        industries=@("human-resources","recruitment","enterprise")
        capabilities=@("talent-matching","churn-prediction","workforce-planning")
        tags=@("DEI","remote-work","skills-gap","retention")
    },
    @{
        name="RealEstate-Scout"; company="PropTech Ventures"
        description="Commercial real estate market analysis and investment opportunity identification"
        industries=@("real-estate","investment","construction")
        capabilities=@("market-valuation","investment-analysis","geospatial-analysis")
        tags=@("CRE","cap-rate","REIT","vacancy-rates","urban-planning")
    },
    @{
        name="AgriSense-Bot"; company="FarmFuture AI"
        description="Precision agriculture analytics, crop yield prediction and sustainability reporting"
        industries=@("agriculture","sustainability","food-tech")
        capabilities=@("crop-modeling","yield-prediction","sustainability-reporting")
        tags=@("precision-ag","soil-health","carbon-farming","food-security")
    }
)

foreach ($agent in $agents) {
    $body = @{
        name = $agent.name
        company = $agent.company
        description = $agent.description
        industries = $agent.industries
        capabilities = $agent.capabilities
        tags = $agent.tags
    } | ConvertTo-Json

    try {
        $response = Invoke-RestMethod -Uri "$API_BASE/agents/register" `
            -Method POST -Body $body -ContentType "application/json"
        Write-Host "[OK] Registered: $($agent.name)" -ForegroundColor Green
    } catch {
        Write-Host "[SKIP] $($agent.name): $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

Write-Host "Done. Run the backend and visit http://localhost:3000" -ForegroundColor Cyan
