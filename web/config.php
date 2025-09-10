<?php
return [
    0 => 'config_placeholder', // Reserved for future use
    1 => $_ENV['DELEGATION_PRODUCERS_URL'] ?? 'https://minaprotocol.com/delegation-program', // URL for delegated block producers link
    'DELEGATION_FORM_URL' => $_ENV['DELEGATION_FORM_URL'] ?? 'https://docs.google.com/forms/d/e/1FAIpQLSduM5EIpwZtf5ohkVepKzs3q0v0--FDEaDfbP2VD4V6GcBepA/viewform',
    'DELEGATION_POLICY_URL' => $_ENV['DELEGATION_POLICY_URL'] ?? 'https://minaprotocol.com/blog/mina-foundation-delegation-policy',
    'DELEGATION_GUIDELINES_URL' => $_ENV['DELEGATION_GUIDELINES_URL'] ?? 'https://docs.minaprotocol.com/node-operators/delegation-program',
    'API_DOCS_URL' => $_ENV['API_DOCS_URL'] ?? 'https://uptime.minaprotocol.com/apidocs/',
    'FOUNDATION_PROGRAM_URL' => $_ENV['FOUNDATION_PROGRAM_URL'] ?? 'https://docs.minaprotocol.com/en',
    'FOUNDATION_GUIDELINES_URL' => $_ENV['FOUNDATION_GUIDELINES_URL'] ?? 'https://docs.minaprotocol.com/en/advanced/foundation-delegation-program',
];