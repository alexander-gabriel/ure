/*
 * opencog/embodiment/Control/PredicateUpdaters/NearPredicateUpdater.cc
 *
 * Copyright (C) 2002-2009 Novamente LLC
 * All Rights Reserved
 * Author(s): Ari Heljakka, Welter Luigi, Samir Araujo
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


#include <opencog/atomspace/SimpleTruthValue.h>

#include "NearPredicateUpdater.h"
#include <opencog/embodiment/AtomSpaceExtensions/AtomSpaceUtil.h>

using namespace OperationalPetController;
using namespace opencog;

NearPredicateUpdater::NearPredicateUpdater(AtomSpace &_atomSpace) :
        BasicPredicateUpdater(_atomSpace) {}

NearPredicateUpdater::~NearPredicateUpdater()
{
}

void NearPredicateUpdater::update(Handle object, Handle pet, unsigned long timestamp )
{
    // there is no map, no update is possible
    Handle spaceMapHandle = atomSpace.getSpaceServer().getLatestMapHandle();
    if (spaceMapHandle == Handle::UNDEFINED) {
        return;
    }
    const SpaceServer::SpaceMap& spaceMap = atomSpace.getSpaceServer().getLatestMap();

    std::vector<std::string> entities;
    spaceMap.findAllEntities(back_inserter(entities));

    logger().debug( "NearPredicateUpdater::%s - Processing timestamp '%lu'", __FUNCTION__, timestamp );
    if ( lastTimestamp != timestamp ) {
        lastTimestamp = timestamp;
        processedEntities.clear( );
    } // if
    
    const std::string& entityAId = atomSpace.getName( object );
    if ( processedEntities.find( entityAId ) != processedEntities.end( ) ) {
        return;
    } // if
    processedEntities.insert( entityAId );

    const Spatial::EntityPtr& entityA = spaceMap.getEntity( entityAId );
    
    bool mapContainsEntity = spaceMap.containsObject( entityAId );

    unsigned int i;
    for( i = 0; i < entities.size( ); ++i ) {        
        const std::string& entityBId = entities[i];
        if ( processedEntities.find( entityBId ) != processedEntities.end( ) ) {
            continue;
        } // if
        Handle entityBHandle = getHandle( entityBId );

        if ( !mapContainsEntity ) {
            logger().debug( "NearPredicateUpdater::%s - Removing predicates from '%s' and '%s'", __FUNCTION__, entityAId.c_str( ), entityBId.c_str( ) );
            setPredicate( object, entityBHandle, "near", 0.0f );
            setPredicate( object, entityBHandle, "next", 0.0f );
        } else {
            const Spatial::EntityPtr& entityB = spaceMap.getEntity( entityBId );
            double distance = entityA->distanceTo( entityB );
            logger().debug( "NearPredicateUpdater::%s - Adding predicates for '%s' and '%s'. distance '%f'", __FUNCTION__, entityAId.c_str( ), entityBId.c_str( ), distance );            
            // distance to near 3,125%
            double nearDistance = ( spaceMap.xMax( ) - spaceMap.xMin( ) ) * 0.003125;
            // distance to next 10,0%
            double nextDistance = ( spaceMap.xMax( ) - spaceMap.xMin( ) ) * 0.1;
            
            setPredicate( object, entityBHandle, "near", ( distance < nearDistance ) ? 1.0f : 0.0f );
            setPredicate( object, entityBHandle, "next", ( distance < nextDistance ) ? 1.0f : 0.0f );
        } // else
    } // for
        
}

void NearPredicateUpdater::setPredicate( const Handle& entityA, const Handle& entityB, const std::string& predicateName, float mean )
{
    
    SimpleTruthValue tv( mean, 1 );
    const std::string& entityAId = atomSpace.getName( entityA );
    const std::string& entityBId = atomSpace.getName( entityB );

    AtomSpaceUtil::setPredicateValue( atomSpace, predicateName, tv, entityA, entityB );
    AtomSpaceUtil::setPredicateValue( atomSpace, predicateName, tv, entityB, entityA );

    { // defining isNear
        static std::map<std::string, Handle> elements;
        elements["Figure"] = entityA;
        elements["Ground"] = entityB;
        elements["Relation_type"] = atomSpace.addNode( CONCEPT_NODE, "is_" + predicateName );
        
        AtomSpaceUtil::setPredicateFrameFromHandles( 
           atomSpace, "#Locative_relation", entityAId + "_" + entityBId + "_" + predicateName, 
              elements, tv );
    } // end block
}
