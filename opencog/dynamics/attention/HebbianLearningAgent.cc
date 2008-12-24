/*
 * opencog/dynamics/attention/HebbianLearningAgent.cc
 *
 * Copyright (C) 2008 by Singularity Institute for Artificial Intelligence
 * Written by Joel Pitt <joel@fruitionnz.com>
 * All Rights Reserved
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License v3 as
 * published by the Free Software Foundation and including the exceptions
 * at http://opencog.org/wiki/Licenses
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program; if not, write to:
 * Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 */
#include "HebbianLearningAgent.h"

#include <opencog/atomspace/AtomSpace.h>
#include <opencog/atomspace/Link.h>
#include <opencog/atomspace/SimpleTruthValue.h>
#include <opencog/server/CogServer.h>
#include <opencog/util/Config.h>

using namespace opencog;

HebbianLearningAgent::HebbianLearningAgent()
{
    static const std::string defaultConfig[] = {
        "ECAN_CONVERT_LINKS","false",
        "ECAN_CONVERSION_THRESHOLD","15",
        "",""
    };
    setParameters(defaultConfig);

    convertLinks = config().get_bool("ECAN_CONVERT_LINKS");
    conversionThreshold = config().get_int("ECAN_CONVERSION_THRESHOLD");

    // Provide a logger, but disable it initially
    log = NULL;
    setLogger(new opencog::Logger("HebbianLearningAgent.log", Logger::WARN, true));
    log->disable();
}

HebbianLearningAgent::~HebbianLearningAgent()
{
    if (log) delete log;
}

void HebbianLearningAgent::setLogger(Logger* _log)
{
    if (log) delete log;
    log = _log;
}

Logger* HebbianLearningAgent::getLogger()
{
    return log;
}

void HebbianLearningAgent::run(CogServer *server)
{
    a = server->getAtomSpace();
    hebbianLearningUpdate();
}

void HebbianLearningAgent::hebbianLearningUpdate()
{
    HandleEntry *links, *current_l;

    // tc affects the truthvalue
    float tc, old_tc, new_tc;
    float tcDecayRate = 0.1f;

    log->info("HebbianLearningAgent::hebbianLearningupdate "
                   "(convert links = %d)", convertLinks);

    // get links again to include the new ones
    links = a->getAtomTable().getHandleSet(HEBBIAN_LINK, true);

    for (current_l = links; current_l; current_l = current_l->next) {
        // for each hebbian link, find targets, work out conjunction and convert
        // that into truthvalue change. the change should be based on existing TV.
        Handle h;
        std::vector<Handle> outgoing;
		bool isDifferent = false;

        h = current_l->handle;

        // get out going set
        outgoing = dynamic_cast<Link *>(TLB::getAtom(h))->getOutgoingSet();
        new_tc = targetConjunction(outgoing);
        // old link strength decays
        old_tc = a->getTV(h).getMean();
		if (new_tc != old_tc) isDifferent = true;

        if (convertLinks && a->getLTI(h) < conversionThreshold) {
            // If mind agent is set to convert hebbian links then
            // inverse and symmetric links will convert between one
            // another when conjunction between sti values is correct
            // (initially for hopfield emulation, but could
            // be useful in other cases)
            if (TLB::getAtom(h)->getType() == INVERSE_HEBBIAN_LINK) {
                // if inverse normalised sti of source is negative
                // (i.e. hebbian link is pointing in the wrong direction)
                if (a->getNormalisedSTI(outgoing[0]) < 0.0f) {
                    tc = (tcDecayRate * new_tc) + ( (1.0f - tcDecayRate) * old_tc);
                    if (tc < 0) {
                        // link no longer representative
                        // swap inverse hebbian link direction
                        log->fine("HebbianLearningAgent: swapping direction of inverse link %s", TLB::getAtom(h)->toString().c_str());
                        // save STI/LTI
                        AttentionValue backupAV = a->getAV(h);
                        a->removeAtom(h);
                        outgoing = moveSourceToFront(outgoing);
                        h = a->addLink(INVERSE_HEBBIAN_LINK, outgoing, SimpleTruthValue(-tc, 0));
                        // restore STI/LTI
                        a->setAV(h,backupAV);
                    }
                // else source is +ve, as it should be
                } else {
                    // Work out whether to convert to symmetric, if not, just
                    // update weight
                    tc = (tcDecayRate * -new_tc) + ( (1.0f - tcDecayRate) * old_tc);

                    if (tc < 0) {
                        // Inverse link no longer representative
                        // change to symmetric hebbian link
                        log->fine("HebbianLearningAgent: change old inverse %s to sym link", TLB::getAtom(h)->toString().c_str());
                        // save STI/LTI
                        AttentionValue backupAV = a->getAV(h);
                        a->removeAtom(h);
                        h = a->addLink(SYMMETRIC_HEBBIAN_LINK, outgoing, SimpleTruthValue(-tc, 1));
                        // restore STI/LTI
                        a->setAV(h,backupAV);
                    } else {
                        // link type is fine, just update TV
                        a->setMean(h, tc);
                    }
                }
            } else {
                tc = (tcDecayRate * new_tc) + ( (1.0f - tcDecayRate) * old_tc);
                if (tc < 0) {
                    // link no longer representative
                    // change to inverse hebbian link
                    log->fine("HebbianLearningAgent: change old sym %s to inverse link", TLB::getAtom(h)->toString().c_str());
                    // save STI/LTI
                    AttentionValue backupAV = a->getAV(h);
                    a->removeAtom(h);
                    outgoing = moveSourceToFront(outgoing);
                    h = a->addLink(INVERSE_HEBBIAN_LINK, outgoing, SimpleTruthValue(-tc, 0));
                    // restore STI/LTI
                    a->setAV(h,backupAV);
                } else {
                    // link type is fine, just update TV
                    a->setMean(h, tc);
                }
            }

        } else {
            // otherwise just update link weights
            // if inverse normalised sti of source is positive
            // (i.e. hebbian link is pointing in the right direction)
            if (TLB::getAtom(h)->getType() == INVERSE_HEBBIAN_LINK &&
                    a->getNormalisedSTI(outgoing[0]) < 0.0f) {
				new_tc = -new_tc;
            }
            tc = (tcDecayRate * new_tc) + ( (1.0f - tcDecayRate) * old_tc);
            if (tc < 0.0f) tc = 0.0f;
            a->setMean(h, tc);
        }
		if (isDifferent)
			log->fine("HebbianLearningAgent: %s old tv %f", TLB::getAtom(h)->toString().c_str(), old_tc);

    }
    // if not enough links, try and create some more either randomly
    // or by looking at what nodes are in attentional focus

    delete links;

}


std::vector<Handle>& HebbianLearningAgent::moveSourceToFront(std::vector<Handle> &outgoing)
{
    // find source, atom with positive norm_sti, and make first in outgoing
    std::vector<Handle>::iterator outgoing_i;
    Handle theSource;
    bool foundTheSource = false;
    for (outgoing_i = outgoing.begin(); outgoing_i < outgoing.end();) {
        float normsti;
        Handle oh = *outgoing_i;
        normsti = a->getNormalisedSTI(oh);
        if (normsti > 0.0f) {
            theSource = oh;
            foundTheSource = true;
            outgoing_i = outgoing.erase(outgoing_i);
        } else
            outgoing_i++;
    }
    if (foundTheSource) {
        outgoing.insert(outgoing.begin(), theSource);
    } else {
        log->error("Can't find source atom for new Asymmetric Hebbian Link");
    }
    return outgoing;

}
float HebbianLearningAgent::targetConjunction(std::vector<Handle> handles)
{
    // TODO: this won't work for Hebbian Links with arity > 2

    // indicates whether at least one of the source/target are
    // in the attentional focus
    bool inAttention = false;
    std::vector<Handle>::iterator h_i;
    Handle h;
    AttentionValue::sti_t sti;
    float tc = 0.0f, normsti;
    std::vector<float> normsti_v;
    bool tcInit = true;

	log->fine("HebbianLearningAgent::targetConjunction");

    for (h_i = handles.begin();
            h_i != handles.end();
            h_i++) {
        h = *h_i;
        sti = a->getSTI(h);

        // if none in attention return 0 at end
        if (sti > a->getAttentionalFocusBoundary()) {
			log->fine("HebbianLearningAgent: %d in attention, focus boundary = %d", sti,
					a->getAttentionalFocusBoundary() );
			inAttention = true;
		}

        // normalise each sti and multiply each
        normsti = a->getNormalisedSTI(h);

        // For debugging:
        normsti_v.push_back(normsti);

        if (tcInit) {
            tc = normsti;
            tcInit = false;
        } else tc *= normsti;
		log->fine("HebbianLearningAgent: normsti %.3f, tc %.3f", normsti, tc);

    }

    if (!inAttention) return 0.0f;


    // cap conjunction to range [-1,1]
    if (tc > 1.0f) tc = 1.0f;
    if (tc < -1.0f) tc = -1.0f;

    log->fine("HebbianLearningAgent: normstis [%.3f,%.3f], tc = %.3f", normsti_v[0], normsti_v[1], tc);

    return tc;

}
