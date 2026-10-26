#!/usr/bin/env perl
# coverage_report.pl - Generate coverage reports from gcov/lcov trace data
# Parses lcov .info files, calculates per-file and per-function coverage,
# generates markdown summary, flags files below threshold

use strict;
use warnings;
use Getopt::Long;
use File::Basename;
use POSIX qw(strftime);

my $input_file     = 'reports/coverage.info';
my $prev_file      = '';
my $output_md      = 'reports/coverage_summary.md';
my $line_threshold = 90;
my $branch_threshold = 95;
my $help           = 0;

GetOptions(
    'input=s'            => \$input_file,
    'previous=s'         => \$prev_file,
    'output=s'           => \$output_md,
    'line-threshold=i'   => \$line_threshold,
    'branch-threshold=i' => \$branch_threshold,
    'help'               => \$help,
) or die "Error in command line arguments\n";

if ($help) {
    print "Usage: $0 [--input FILE] [--previous FILE] [--output FILE] [--line-threshold N] [--branch-threshold N]\n";
    exit 0;
}

my $current  = parse_lcov($input_file);
my $previous = $prev_file ? parse_lcov($prev_file) : {};

# Calculate totals
my ($total_lines_hit, $total_lines_found) = (0, 0);
my ($total_branches_hit, $total_branches_found) = (0, 0);
my @below_threshold;

for my $file (sort keys %$current) {
    my $c = $current->{$file};
    $total_lines_hit    += $c->{lines_hit};
    $total_lines_found  += $c->{lines_found};
    $total_branches_hit += $c->{branches_hit};
    $total_branches_found += $c->{branches_found};

    my $line_pct = $c->{lines_found} > 0 ? ($c->{lines_hit} / $c->{lines_found}) * 100 : 0;
    if ($line_pct < $line_threshold) {
        push @below_threshold, { file => $file, line_pct => $line_pct };
    }
}

my $overall_line_pct   = $total_lines_found > 0   ? ($total_lines_hit / $total_lines_found) * 100     : 0;
my $overall_branch_pct = $total_branches_found > 0 ? ($total_branches_hit / $total_branches_found)*100 : 0;

# Generate markdown report
my $timestamp = strftime("%Y-%m-%d %H:%M:%S", localtime);
open my $fh, '>', $output_md or die "Cannot open $output_md: $!\n";

print $fh "# Coverage Report\n\n";
print $fh "**Generated:** $timestamp\n\n";
print $fh "## Summary\n\n";
printf $fh "| Metric           | Hit   | Total | Coverage |\n";
printf $fh "|------------------|-------|-------|----------|\n";
printf $fh "| Line Coverage    | %d | %d | %.1f%% |\n", $total_lines_hit, $total_lines_found, $overall_line_pct;
printf $fh "| Branch Coverage  | %d | %d | %.1f%% |\n\n", $total_branches_hit, $total_branches_found, $overall_branch_pct;

# Coverage delta from previous run
if ($prev_file && %$previous) {
    my ($prev_lh, $prev_lf) = (0, 0);
    for my $file (keys %$previous) {
        $prev_lh += $previous->{$file}{lines_hit};
        $prev_lf += $previous->{$file}{lines_found};
    }
    my $prev_pct = $prev_lf > 0 ? ($prev_lh / $prev_lf) * 100 : 0;
    my $delta = $overall_line_pct - $prev_pct;
    my $indicator = $delta >= 0 ? "+" : "";
    printf $fh "**Coverage Delta:** %s%.2f%%\n\n", $indicator, $delta;
}

# Per-file table
print $fh "## Per-File Coverage\n\n";
print $fh "| File | Lines Hit | Lines Total | Coverage | Status |\n";
print $fh "|------|-----------|-------------|----------|--------|\n";
for my $file (sort keys %$current) {
    my $c = $current->{$file};
    my $pct = $c->{lines_found} > 0 ? ($c->{lines_hit} / $c->{lines_found}) * 100 : 0;
    my $status = $pct >= $line_threshold ? "PASS" : "**BELOW**";
    my $short = basename($file);
    printf $fh "| %s | %d | %d | %.1f%% | %s |\n", $short, $c->{lines_hit}, $c->{lines_found}, $pct, $status;
}

# Files below threshold
if (@below_threshold) {
    print $fh "\n## Files Below Threshold ($line_threshold%)\n\n";
    for my $entry (sort { $a->{line_pct} <=> $b->{line_pct} } @below_threshold) {
        printf $fh "- **%s**: %.1f%%\n", basename($entry->{file}), $entry->{line_pct};
    }
}

# Uncovered functions
print $fh "\n## Uncovered Functions\n\n";
for my $file (sort keys %$current) {
    my $c = $current->{$file};
    next unless $c->{uncovered_functions} && @{$c->{uncovered_functions}};
    printf $fh "### %s\n", basename($file);
    for my $fn (@{$c->{uncovered_functions}}) {
        printf $fh "- `%s`\n", $fn;
    }
}

close $fh;
printf "Coverage report written to %s (line=%.1f%%, branch=%.1f%%)\n", $output_md, $overall_line_pct, $overall_branch_pct;

# --- Subroutines ---

sub parse_lcov {
    my ($path) = @_;
    my %data;
    open my $fh, '<', $path or do { warn "Cannot open $path: $!"; return {}; };

    my $current_file = '';
    while (<$fh>) {
        chomp;
        if (/^SF:(.+)/) {
            $current_file = $1;
            $data{$current_file} //= {
                lines_hit => 0, lines_found => 0,
                branches_hit => 0, branches_found => 0,
                functions => {}, uncovered_functions => [],
            };
        } elsif (/^LH:(\d+)/) {
            $data{$current_file}{lines_hit} = $1;
        } elsif (/^LF:(\d+)/) {
            $data{$current_file}{lines_found} = $1;
        } elsif (/^BRH:(\d+)/) {
            $data{$current_file}{branches_hit} = $1;
        } elsif (/^BRF:(\d+)/) {
            $data{$current_file}{branches_found} = $1;
        } elsif (/^FN:\d+,(.+)/) {
            $data{$current_file}{functions}{$1} = 0;
        } elsif (/^FNDA:(\d+),(.+)/) {
            $data{$current_file}{functions}{$2} = $1;
            if ($1 == 0) {
                push @{$data{$current_file}{uncovered_functions}}, $2;
            }
        }
    }
    close $fh;
    return \%data;
}
