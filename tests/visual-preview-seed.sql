-- Synthetic data used only by the disposable GitHub Actions visual-preview database.
-- Never execute this file against a production or shared database.

INSERT INTO khs_requests (
    request_id, request_date, request_subject, requester_owner
) VALUES
    ('REQ-VIS-001', DATE '2026-11-10', 'Cloud Infrastructure & Managed Services', 'IT Procurement'),
    ('REQ-VIS-002', DATE '2026-10-02', 'Network Connectivity and MPLS Renewal', 'Technology Sourcing'),
    ('REQ-VIS-003', DATE '2026-09-18', 'Enterprise Software Licensing', 'Digital Workplace'),
    ('REQ-VIS-004', DATE '2026-11-03', 'Facilities and Workplace Services', 'General Procurement')
ON CONFLICT (request_id) DO NOTHING;

INSERT INTO khs_items (
    khs_id, request_id, source_row_no, dispatch_date, executor_code,
    subtype, vendor_name, contract_start_date, contract_end_date,
    boq_confirmation_date, negotiation_date, final_negotiation_date,
    mi_head_approval_date, mi_sm_approval_date, mi_gm_approval_date,
    legal_submission_date, lp_circulation_start_date,
    lp_contract_team_completion_date, lp_junior_manager_approval_date,
    lp_senior_manager_approval_date, lp_gm_scm_approval_date,
    lp_completion_date, khs_inject_start_date, khs_inject_completion_date,
    waiting_for, waiting_reason, last_updated_date, remarks
) VALUES
    (
        'KHS-VIS-001', 'REQ-VIS-001', 5, DATE '2026-11-12', 'FZK',
        'Renewal', 'Aster Cloud Services', DATE '2024-12-01', DATE '2027-11-30',
        NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
        NULL, NULL, NULL, NULL, NULL, NULL, NULL,
        'Business Unit', 'Final scope confirmation before BOQ freeze',
        DATE '2026-11-14', 'Synthetic visual-preview record'
    ),
    (
        'KHS-VIS-002', 'REQ-VIS-001', 6, DATE '2026-09-01', 'ALW',
        'Kontrak Baru', 'Meridian Technology Partners', DATE '2026-10-01', DATE '2027-12-31',
        DATE '2026-09-04', DATE '2026-09-10', DATE '2026-09-14',
        DATE '2026-09-17', DATE '2026-09-20', NULL,
        NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
        'General Manager', 'GM approval is pending',
        DATE '2026-11-13', 'Synthetic visual-preview record'
    ),
    (
        'KHS-VIS-003', 'REQ-VIS-002', 8, DATE '2026-09-15', 'FZK',
        'Renewal', 'Nusantara Network Integrators', DATE '2024-10-01', DATE '2027-09-30',
        DATE '2026-09-18', DATE '2026-09-22', DATE '2026-09-25',
        DATE '2026-09-26', DATE '2026-09-28', DATE '2026-10-20',
        DATE '2026-10-22', DATE '2026-10-25',
        NULL, NULL, NULL, NULL, NULL, NULL, NULL,
        'Tim Kontrak', 'LP package is being checked by the contract team',
        DATE '2026-11-14', 'Synthetic visual-preview record'
    ),
    (
        'KHS-VIS-004', 'REQ-VIS-002', 9, DATE '2026-08-20', 'AME',
        'Kontrak Baru', 'Pacific Fiber Solutions', DATE '2026-10-01', DATE '2028-09-30',
        DATE '2026-08-23', DATE '2026-08-26', DATE '2026-08-28',
        DATE '2026-08-29', DATE '2026-08-31', DATE '2026-09-28',
        DATE '2026-09-29', DATE '2026-10-01',
        DATE '2026-10-02', DATE '2026-10-05', NULL,
        NULL, NULL, NULL, NULL,
        'Senior Manager Strategic Sourcing', 'Awaiting senior manager approval',
        DATE '2026-11-12', 'Synthetic visual-preview record'
    ),
    (
        'KHS-VIS-005', 'REQ-VIS-003', 11, DATE '2026-08-10', 'ALW',
        'Renewal', 'Orion Enterprise Software', DATE '2025-01-01', DATE '2027-08-31',
        DATE '2026-08-13', DATE '2026-08-16', DATE '2026-08-18',
        DATE '2026-08-19', DATE '2026-08-21', DATE '2026-09-18',
        DATE '2026-09-19', DATE '2026-09-20',
        DATE '2026-09-21', DATE '2026-09-22', DATE '2026-09-24',
        NULL, NULL, NULL, NULL,
        'GM SCM', 'Final LP approval is pending',
        DATE '2026-11-11', 'Synthetic visual-preview record'
    ),
    (
        'KHS-VIS-006', 'REQ-VIS-003', 12, DATE '2026-07-20', 'FZK',
        'Renewal', 'Vertex Digital Workplace', DATE '2025-01-20', DATE '2027-01-31',
        DATE '2026-07-22', DATE '2026-07-23', DATE '2026-07-24',
        DATE '2026-07-25', DATE '2026-07-26', DATE '2026-07-27',
        DATE '2026-07-29', DATE '2026-08-01',
        DATE '2026-08-02', DATE '2026-08-03', DATE '2026-08-05',
        DATE '2026-08-07', DATE '2026-08-08', DATE '2026-08-10',
        DATE '2026-08-11', NULL, NULL, DATE '2026-08-11',
        'Synthetic fully injected contract approaching renewal'
    ),
    (
        'KHS-VIS-007', 'REQ-VIS-004', 14, DATE '2026-07-01', 'AME',
        'Kontrak Baru', 'Cendana Workplace Services', DATE '2025-05-15', DATE '2027-05-31',
        DATE '2026-07-03', DATE '2026-07-06', DATE '2026-07-08',
        DATE '2026-07-09', DATE '2026-07-10', DATE '2026-07-11',
        DATE '2026-07-12', DATE '2026-07-14',
        DATE '2026-07-15', DATE '2026-07-16', DATE '2026-07-17',
        DATE '2026-07-20', DATE '2026-07-21', DATE '2026-07-23',
        DATE '2026-07-24', NULL, NULL, DATE '2026-07-24',
        'Synthetic fully injected contract for lifecycle watch'
    ),
    (
        'KHS-VIS-008', 'REQ-VIS-004', 15, DATE '2026-05-01', 'FZK',
        'Renewal', 'Sagara Integrated Facility', DATE '2024-11-10', DATE '2026-11-10',
        DATE '2026-05-04', DATE '2026-05-07', DATE '2026-05-09',
        DATE '2026-05-10', DATE '2026-05-11', DATE '2026-05-12',
        DATE '2026-05-13', DATE '2026-05-15',
        DATE '2026-05-16', DATE '2026-05-18', DATE '2026-05-19',
        DATE '2026-05-21', DATE '2026-05-22', DATE '2026-05-24',
        DATE '2026-05-25', NULL, NULL, DATE '2026-05-25',
        'Synthetic fully injected contract showing an expired lifecycle state'
    ),
    (
        'KHS-VIS-009', 'REQ-VIS-004', 16, DATE '2026-10-15', 'ALW',
        'Kontrak Baru', 'Bumi Sarana Teknologi', DATE '2026-11-01', DATE '2028-10-31',
        DATE '2026-10-17', DATE '2026-10-20', DATE '2026-10-22',
        DATE '2026-10-23', DATE '2026-10-24', DATE '2026-10-25',
        DATE '2026-10-27', DATE '2026-10-29',
        DATE '2026-10-30', DATE '2026-10-31', DATE '2026-11-01',
        DATE '2026-11-03', DATE '2026-11-04', NULL, NULL,
        'KHS Injection Team', 'Injection is in progress',
        DATE '2026-11-14', 'Synthetic visual-preview record'
    )
ON CONFLICT (khs_id) DO NOTHING;
